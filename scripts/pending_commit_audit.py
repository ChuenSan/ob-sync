#!/usr/bin/env python3
"""只读检查待提交候选；不暂存、不提交、不联网。仅使用 Python 标准库。"""
from __future__ import annotations

import argparse
import collections
import ctypes
import datetime as dt
import json
import os
from pathlib import Path
import re
import stat
import struct
import subprocess
import sys
import time

# 路径规则只决定初筛，不把扫描未命中等同于安全。
PRUNED_DIRS = {".git", "node_modules", "__pycache__", ".cache", ".venv", "venv", "dist", "build", "target"}
LOCAL_DIRS = {".obsidian", ".claudian", ".trash", ".potplayer_timestamp", ".mindfs", ".idea", ".vscode", ".stfolder"}
KEY_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".keystore"}
PATTERNS = {
    "私钥": re.compile(rb"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----"),
    "疑似 API Key/Token": re.compile(
        rb"(?<![A-Za-z0-9])(?:sk-(?:proj-|ant-api\d+-)?[A-Za-z0-9_-]{20,}|"
        rb"gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{30,}|"
        rb"AKIA[A-Z0-9]{16}|AIza[A-Za-z0-9_-]{30,})(?![A-Za-z0-9])"
    ),
    "带凭据的 URL": re.compile(
        rb"(?:https?|mysql|postgres(?:ql)?|mongodb(?:\+srv)?|redis)://[^\s/:<>\"']{1,100}:[^\s/@<>\"']{1,100}@"
    ),
    "疑似密码/认证配置": re.compile(
        rb"(?i)(?:api[_-]?key|access[_-]?token|client[_-]?secret|password|passwd|"
        rb"authorization|cookie)[\x20\t\"']{0,4}[:=][\x20\t\"']{0,4}[^\s\"',;<>`]{6,}"
    ),
    "疑似 Bearer/JWT 凭据": re.compile(
        rb"(?i)\bBearer[ \t]+[A-Za-z0-9_.~+/-]{20,}|\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"
    ),
}
PERSONAL_PATTERN = re.compile(r"(?:身份证(?:号码|号)?|手机(?:号码|号)?)[^\d\n]{0,8}(?:\d{17}[\dXx]|1[3-9]\d{9})(?!\d)")


class AuditError(Exception):
    pass


def git(repo: Path, *args: str, data: bytes | None = None, allowed=(0,)) -> subprocess.CompletedProcess:
    env = dict(os.environ, GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0")
    result = subprocess.run(
        ["git", "-C", str(repo), *args], input=data, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, env=env, check=False,
    )
    if result.returncode not in allowed:
        # 不回显 stderr：外部 Git 配置/凭据可能出现在错误消息中。
        raise AuditError(f"git {args[0]} 失败（退出码 {result.returncode}）")
    return result


def decode(value: bytes) -> str:
    return os.fsdecode(value)


def split_paths(value: bytes) -> list[str]:
    return [decode(p) for p in value.split(b"\0") if p]


def parse_status(raw: bytes) -> dict[str, dict]:
    fields = iter(raw.split(b"\0"))
    changes = {}
    for field in fields:
        if not field:
            continue
        status = decode(field[:2])
        path = decode(field[3:]).rstrip("/")
        row = {"path": path, "status": status, "original_path": None}
        if "R" in status or "C" in status:
            row["original_path"] = decode(next(fields))
        changes[path] = row
    return changes


def iso(timestamp: float | None) -> str | None:
    return dt.datetime.fromtimestamp(timestamp).astimezone().isoformat(timespec="microseconds") if timestamp is not None else None


class BirthTime:
    """macOS 使用 st_birthtime；Linux 按 statx ABI 获取 btime，不用 ctime 冒充。"""
    def __init__(self):
        self.statx = None
        if sys.platform.startswith("linux"):
            self.libc = ctypes.CDLL(None, use_errno=True)
            self.statx = getattr(self.libc, "statx", None)
            if self.statx:
                self.statx.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_uint, ctypes.c_void_p]
                self.statx.restype = ctypes.c_int

    def get(self, path: Path, metadata: os.stat_result) -> float | None:
        native = getattr(metadata, "st_birthtime", None)
        if native is not None:
            return native
        if self.statx:
            buffer = ctypes.create_string_buffer(256)
            # AT_FDCWD, AT_SYMLINK_NOFOLLOW, STATX_BTIME
            if self.statx(-100, os.fsencode(path), 0x100, 0x800, buffer) == 0:
                if struct.unpack_from("=I", buffer.raw, 0)[0] & 0x800:
                    seconds, nanos = struct.unpack_from("=qI", buffer.raw, 80)
                    return seconds + nanos / 1_000_000_000
        return None


def path_policy(path: str) -> tuple[str | None, list[str]]:
    parts = Path(path).parts
    name = parts[-1] if parts else path
    if name == ".DS_Store" or name.startswith("._"):
        return "exclude", ["macOS 元数据"]
    if name == ".env" or name.startswith(".env."):
        return "exclude", ["环境变量/本地凭据文件"]
    if any(p in PRUNED_DIRS | LOCAL_DIRS for p in parts):
        return "exclude", ["缓存、依赖、构建产物或本地/IDE 配置"]
    if name in {".stignore", ".gcm-diagnose.log.local", ".export"} or name.endswith((".log", ".tmp", ".swp", ".bak")) or name.endswith("~"):
        return "exclude", ["同步配置、日志或临时备份"]
    if parts[:2] == ("YOLO", "data") or (parts[:2] == ("YOLO", "Exports") and name.endswith(".json")):
        return "exclude", ["本地 AI 会话/配置数据"]
    if parts and parts[0] == "0-个人信息":
        return "exclude", ["个人敏感信息目录"]
    if Path(name).suffix.lower() in KEY_SUFFIXES:
        return "review", ["密钥/证书类文件，需确认是否含私钥"]
    if parts and parts[0] in {"日志", "目标", "YOLO"}:
        return "review", ["个人记录/AI 导出内容，需确认隐私及提交用途"]
    if name == "backup.md":
        return "review", ["备份文档，需确认是否属于提交范围"]
    return None, []


def is_binary(data: bytes) -> bool:
    signatures = (b"%PDF-", b"PK\x03\x04", b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"GIF87a", b"GIF89a", b"RIFF", b"\xd0\xcf\x11\xe0", b"\x7fELF")
    return b"\0" in data[:8192] or data.startswith(signatures)


def inspect_bytes(data: bytes, source: str) -> tuple[list[dict], list[str]]:
    # 二进制不进入文本正则扫描，也不能因此进入可提交候选。
    if is_binary(data):
        return [], [f"{source}：二进制附件，无法自动核实隐私/用途"]
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return [], [f"{source}：非 UTF-8 内容，需人工检查"]
    findings = []
    for label, pattern in PATTERNS.items():
        matches = list(pattern.finditer(data))
        if matches:
            findings.append({"kind": label, "source": source, "lines": sorted({data.count(b"\n", 0, m.start()) + 1 for m in matches[:20]}), "matches": len(matches)})
    matches = list(PERSONAL_PATTERN.finditer(text))
    if matches:
        findings.append({"kind": "疑似身份证/手机号", "source": source, "lines": sorted({text.count("\n", 0, m.start()) + 1 for m in matches[:20]}), "matches": len(matches)})
    return findings, []


def ignored_paths(repo: Path, paths: set[str]) -> set[str]:
    if not paths:
        return set()
    result = git(repo, "check-ignore", "-z", "--stdin", data=b"\0".join(os.fsencode(p) for p in sorted(paths)) + b"\0", allowed=(0, 1))
    return set(split_paths(result.stdout))


def time_record(metadata: os.stat_result, created: float | None, start: float | None, now: float) -> dict:
    modified_in_window = start is not None and start < metadata.st_mtime <= now
    created_in_window = start is not None and created is not None and start < created <= now
    reasons = []
    if start is None:
        reasons.append("首次提交：无 HEAD 时间基准")
    if modified_in_window:
        reasons.append("mtime 位于时间窗口")
    if created_in_window:
        reasons.append("Birth Time 位于时间窗口")
    return {"mtime": iso(metadata.st_mtime), "birth": iso(created), "time_reasons": reasons,
            "mtime_in_window": modified_in_window, "birth_in_window": created_in_window,
            "future_time": metadata.st_mtime > now or (created is not None and created > now)}


def scan_tree(repo: Path, start: float | None, now: float, birth: BirthTime) -> tuple[dict, set[str], dict]:
    recent = {}
    nested = set()
    stats = {"files": 0, "birth_available": 0, "birth_unavailable": 0, "pruned_directories": 0, "errors": []}

    def error(exc):
        stats["errors"].append({"path": os.path.relpath(exc.filename, repo) if exc.filename else "?", "reason": "目录不可访问"})

    for root, dirs, files in os.walk(repo, followlinks=False, onerror=error):
        base = Path(root)
        if base != repo and ".git" in dirs + files:
            nested.add(base.relative_to(repo).as_posix())
            dirs[:] = []
            continue
        kept = []
        for directory in dirs:
            if directory in PRUNED_DIRS:
                stats["pruned_directories"] += 1
            elif (base / directory).is_symlink():
                files.append(directory)  # 检查链接自身，不遍历或读取其目标。
            else:
                kept.append(directory)
        dirs[:] = kept
        for name in files:
            if name == ".git":  # worktree/submodule 的 .git 也可能是文件。
                continue
            file = base / name
            path = file.relative_to(repo).as_posix()
            try:
                metadata = file.lstat()
                created = birth.get(file, metadata)
                stats["files"] += 1
                stats["birth_available" if created is not None else "birth_unavailable"] += 1
                details = time_record(metadata, created, start, now)
                if details["time_reasons"]:
                    recent[path] = details
            except OSError:
                stats["errors"].append({"path": path, "reason": "文件时间不可读取"})
    return recent, nested, stats


def assess_window(repo: Path, path: str, change: dict, details: dict | None,
                  start: float | None, now: float, birth: BirthTime, nested: set[str]) -> tuple[str, dict | None, str]:
    if start is None:
        return "current", details, "首次提交"
    status = change["status"]
    if "U" in status or status in {"AA", "DD"}:
        return "time_unknown", details, "未解决冲突，禁止提交；需单独确认时间和范围"
    if any(event in status for event in "DRC"):
        return "time_unknown", details, "Git 不记录删除/重命名/复制操作时间，需确认属于本时间段"
    file = repo / path
    if path in nested or file.is_dir():
        return "time_unknown", details, "嵌套仓库/目录的变化时间需单独确认"
    if details is None:
        try:
            metadata = file.lstat()
            details = time_record(metadata, birth.get(file, metadata), start, now)
        except OSError:
            return "time_unknown", None, "文件时间不可获取，不能确认属于本时间段"
    is_new = status == "??" or "A" in status
    if details["future_time"]:
        return "time_unknown", details, "文件时间晚于检查时间，需确认"
    if details["mtime_in_window"] or (is_new and details["birth_in_window"]):
        return "current", details, "变化时间符合本次窗口"
    if is_new and details["birth"] is None:
        return "time_unknown", details, "创建时间不可用且 mtime 不在窗口内，不能确认新增时间"
    return "outside_window", details, "时间不在本次窗口内；不扫描内容，不纳入本次候选"


def deferred_entry(path: str, change: dict, details: dict | None, decision: str, reason: str) -> dict:
    details = details or {}
    return {"path": path, "status": change["status"], "original_path": change.get("original_path"),
            "sources": ["Git 状态"], "mtime": details.get("mtime"), "birth": details.get("birth"),
            "time_reasons": details.get("time_reasons", []), "scope": decision, "decision": decision,
            "reasons": [reason], "findings": [], "scanned_sources": []}


def read_worktree(file: Path, maximum: int) -> bytes:
    # O_NOFOLLOW 防止扫描符号链接；上限同时约束扫描期间增长的文件。
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    descriptor = os.open(file, flags)
    with os.fdopen(descriptor, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise OSError("not a regular file")
        prefix = stream.read(min(8192, maximum + 1))
        if is_binary(prefix):
            return prefix
        return prefix + stream.read(maximum + 1 - len(prefix))


def inspect_entry(repo: Path, path: str, change: dict | None, times: dict | None, ignored: bool,
                  nested: set[str], birth: BirthTime, maximum: int) -> dict:
    status = change["status"] if change else "  "
    row = {"path": path, "status": status, "original_path": change.get("original_path") if change else None,
           "sources": (["Git 状态"] if change else []) + (["文件时间"] if times else []),
           "mtime": None, "birth": None, "time_reasons": times["time_reasons"] if times else [],
           "scope": "current", "decision": "candidate", "reasons": [], "findings": [], "scanned_sources": []}
    if times:
        row.update(mtime=times["mtime"], birth=times["birth"])
    if not change and not ignored:
        # 有 HEAD 且 Git 确认无差异；时间变化不能产生重复提交。
        row.update(decision="unchanged", reasons=["仅时间变化；Git 与 HEAD/索引无差异"])
        return row
    policy, reasons = path_policy(path)
    row["reasons"].extend(reasons)
    conflict = "U" in status or status in {"AA", "DD"}
    if conflict:
        row.update(decision="review")
        row["reasons"].append("未解决的 Git 冲突，禁止提交")
        return row
    if ignored:
        row.update(decision="exclude")
        row["reasons"].append("被 Git 忽略规则排除")
        return row
    if policy == "exclude":
        row["decision"] = "exclude"
        return row
    if policy == "review":
        row["decision"] = "review"
    if "D" in status:
        row["decision"] = "review"
        row["reasons"].append("存在删除，需确认不是意外删除")
    if "R" in status or "C" in status:
        row["decision"] = "review"
        row["reasons"].append("重命名/复制，需核对原路径与新路径")
    file = repo / path
    parent = file.parent
    while parent != repo:
        if parent.is_symlink():
            row["decision"] = "review"
            row["reasons"].append("父目录为符号链接：未读取目标，须单独检查暂存区")
            return row
        parent = parent.parent
    if path in nested or file.is_dir():
        row["decision"] = "review"
        row["reasons"].append("嵌套仓库/目录，不能作为普通文件直接暂存")
        return row
    try:
        metadata = file.lstat()
        row.update(mtime=iso(metadata.st_mtime), birth=iso(birth.get(file, metadata)), size=metadata.st_size)
        if stat.S_ISLNK(metadata.st_mode):
            row["decision"] = "review"
            row["reasons"].append("符号链接：未读取目标，需确认目标和用途")
        elif not stat.S_ISREG(metadata.st_mode):
            row["decision"] = "review"
            row["reasons"].append("不是普通文件，未读取内容")
        else:
            data = read_worktree(file, maximum) if metadata.st_size <= maximum else b""
            if metadata.st_size > maximum or len(data) > maximum:
                row["decision"] = "review"
                row["reasons"].append("工作区内容超过扫描上限，未完整检查")
            else:
                findings, concerns = inspect_bytes(data, "工作区")
                row["findings"].extend(findings)
                row["reasons"].extend(concerns)
                if concerns:
                    row["decision"] = "review"
                if not data.strip():
                    row["decision"] = "review"
                    row["reasons"].append("工作区为空文件，需确认用途")
                row["scanned_sources"].append("工作区")
    except FileNotFoundError:
        if "D" not in status:
            row["decision"] = "review"
            row["reasons"].append("检查时文件不存在，需重新运行")
    except OSError:
        row["decision"] = "review"
        row["reasons"].append("工作区内容无法读取")

    # 不能只扫描工作区：已暂存的秘密可能已在工作区被删除/替换。
    if status[0] not in {" ", "?", "D"}:
        try:
            spec = ":" + path
            size = int(git(repo, "cat-file", "-s", spec).stdout)
            if size > maximum:
                row["decision"] = "review"
                row["reasons"].append("已暂存内容超过扫描上限，未完整检查")
            else:
                data = git(repo, "cat-file", "blob", spec).stdout
                findings, concerns = inspect_bytes(data, "暂存区")
                row["findings"].extend(findings)
                row["reasons"].extend(concerns)
                if concerns:
                    row["decision"] = "review"
                if not data.strip():
                    row["decision"] = "review"
                    row["reasons"].append("暂存区为空文件，需确认用途")
                row["scanned_sources"].append("暂存区")
        except (AuditError, ValueError):
            row["decision"] = "review"
            row["reasons"].append("暂存区内容无法读取（可能是子模块或索引变化）")
    if row["findings"]:
        row["decision"] = "review"
    if any(f["kind"] == "私钥" for f in row["findings"]):
        row["decision"] = "exclude"
        row["reasons"].append("检测到私钥，禁止提交")
    if row["decision"] == "candidate":
        row["reasons"].append("文本初筛通过；仍须核对任务相关性与实际 diff")
    return row


def audit(repo: Path, maximum: int = 8 * 1024 * 1024) -> dict:
    repo = Path(decode(git(repo, "rev-parse", "--show-toplevel").stdout).strip()).resolve()
    now = time.time()
    head = git(repo, "rev-parse", "--verify", "HEAD", allowed=(0, 128))
    has_head = head.returncode == 0
    start = int(git(repo, "log", "-1", "--format=%ct", "HEAD").stdout) if has_head else None
    initial_status = git(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all").stdout
    changes = parse_status(initial_status)
    tracked = set(split_paths(git(repo, "ls-files", "-z", "--cached").stdout))
    birth = BirthTime()
    recent, nested, scan_stats = scan_tree(repo, start, now, birth)
    ignored = ignored_paths(repo, set(recent) - set(changes) - tracked)
    rows = []
    for path in sorted(set(recent) | set(changes)):
        change = changes.get(path)
        details = recent.get(path)
        if change:
            scope, details, reason = assess_window(repo, path, change, details, start, now, birth, nested)
            if scope != "current":
                rows.append(deferred_entry(path, change, details, scope, reason))
                continue
        rows.append(inspect_entry(repo, path, change, details, path in ignored, nested, birth, maximum))
    nested_reports = []
    for path in sorted(nested):
        try:
            nested_changes = parse_status(git(repo / path, "status", "--porcelain=v1", "-z", "--untracked-files=all").stdout)
            nested_reports.append({"path": path, "changes": list(nested_changes.values())})
        except AuditError:
            nested_reports.append({"path": path, "error": "嵌套仓库状态无法读取"})
    # --no-ext-diff / --no-textconv 避免运行仓库定义的外部差异程序；不输出 diff 正文。
    diffs = {}
    for label, extra in (("unstaged", []), ("staged", ["--cached"])):
        result = git(repo, "diff", *extra, "--no-ext-diff", "--no-textconv", "--numstat", "-z")
        diffs[label] = {"has_diff": bool(result.stdout)}
    remotes = decode(git(repo, "remote", "-v").stdout)
    remotes = re.sub(r"(https?://)[^/\s]*@", r"\1[凭据已隐藏]@", remotes)
    remotes = re.sub(r"(https?://[^\s?#]+)[?#][^\s]*", r"\1[参数已隐藏]", remotes)
    final_status = git(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all").stdout
    final_head = git(repo, "rev-parse", "--verify", "HEAD", allowed=(0, 128)).stdout
    return {
        "repository": str(repo), "branch": decode(git(repo, "branch", "--show-current").stdout).strip() or "(detached HEAD)",
        "remotes": remotes.strip(), "head": decode(head.stdout).strip() if has_head else None,
        "commit_time": iso(start), "now": iso(now), "platform": sys.platform,
        "time_candidate_count": len(recent), "git_change_count": len(changes),
        "current_check_count": sum(row["scope"] == "current" for row in rows),
        "counts": dict(collections.Counter(row["decision"] for row in rows)), "files": rows,
        "scan": scan_stats, "nested_repositories": nested_reports, "diffs": diffs,
        "snapshot_changed": initial_status != final_status or head.stdout != final_head,
        "max_bytes": maximum,
        "limitations": [
            "候选是初筛结果，不是自动批准的提交清单；任务相关性和实际 diff 仍需人工核对。",
            "敏感模式可能误报/漏报；示例凭据也需人工确认，不展示或验证凭据值。",
            "二进制、超大文件、不可读文件、符号链接与个人记录不能自动判定安全。",
            "本次只检查时间窗口内的内容；窗口外旧变化仅汇总，删除/重命名等操作时间不明的单列待确认。",
            "嵌套仓库仅汇总状态，不递归批准其内容；已暂存的范围外变化不会自动清除，提交前必须处理。",
            "不获取远程最新状态、不判断是否可以 Push；本报告不是一致性快照，提交前必须重新检查。",
        ],
    }


def display_path(path: str) -> str:
    return json.dumps(path, ensure_ascii=False)  # 转义换行、制表符，避免伪造报告行。


def print_report(report: dict, limit: int):
    print(f"仓库：{report['repository']}\n分支：{report['branch']}\n远程：{report['remotes'] or '(无)'}")
    print(f"时间窗口：{report['commit_time'] or '(无 HEAD，首次提交)'} → {report['now']}")
    print(f"时间扫描命中 {report['time_candidate_count']}；本次待检查 {report['current_check_count']}；Git 状态共 {report['git_change_count']} 项（不等于本次候选）")
    print(f"差异：未暂存={report['diffs']['unstaged']['has_diff']}，已暂存={report['diffs']['staged']['has_diff']}")
    stats = report["scan"]
    print(f"时间扫描 {stats['files']} 个文件；Birth Time 可用 {stats['birth_available']}，不可用 {stats['birth_unavailable']}")
    if stats["birth_unavailable"]:
        print("注意：部分创建时间不可用，未使用 ctime 替代；无法证明在窗口内的新增单列待确认。")
    risky = [r for r in report["files"] if r["findings"]]
    priority = {"私钥": 0, "疑似 API Key/Token": 1, "疑似 Bearer/JWT 凭据": 2, "疑似身份证/手机号": 3}
    risky.sort(key=lambda row: min(priority.get(f["kind"], 4) for f in row["findings"]))
    print(f"\n【敏感风险优先】{len(risky)} 个文件命中（可能误报，不展示凭据值）")
    for row in risky[:limit] if limit else risky:
        print(f"  [{row['status']}] {display_path(row['path'])}")
        for finding in row["findings"]:
            print(f"    {finding['kind']}：{finding['source']} 第 {','.join(map(str, finding['lines']))} 行")
    if limit and len(risky) > limit:
        print(f"  ……另有 {len(risky) - limit} 项；用 --all 或 --json 查看全部。")
    for decision, title in (("candidate", "本时间段待提交候选（文本初筛通过，仍需人工确认）"),
                            ("review", "本时间段需人工复核（不自动纳入提交范围）"),
                            ("exclude", "本时间段应排除（不代表已经取消暂存）"),
                            ("unchanged", "无需重复提交（Git 无内容差异）"),
                            ("time_unknown", "时间待确认（不计入本次候选）")):
        rows = [r for r in report["files"] if r["decision"] == decision]
        print(f"\n【{title}】{len(rows)} 项")
        for row in rows[:limit] if limit else rows:
            print(f"  [{row['status']}] {display_path(row['path'])}")
            if row["original_path"]:
                print(f"    原路径：{display_path(row['original_path'])}")
            print("    " + "；".join(row["reasons"]))
            for finding in row["findings"]:
                print(f"    风险：{finding['kind']}，{finding['source']} 第 {','.join(map(str, finding['lines']))} 行（不显示值）")
        if limit and len(rows) > limit:
            print(f"  ……另有 {len(rows) - limit} 项；用 --all 或 --json 查看全部。")
    historical = [r for r in report["files"] if r["decision"] == "outside_window"]
    print(f"\n【窗口外历史变化】{len(historical)} 项（未扫描内容，不纳入本次候选）")
    if not limit:
        for row in historical:
            print(f"  [{row['status']}] {display_path(row['path'])}")
    elif historical:
        print("  默认仅汇总数量；用 --all 或 --json 查看路径。")
    print("\n【嵌套仓库状态提示（不计入本次候选，操作时间需另行确认）】")
    for nested in report["nested_repositories"]:
        counts = dict(collections.Counter(r["status"] for r in nested.get("changes", [])))
        print(f"  {display_path(nested['path'])}：{nested.get('error', counts)}")
    if not report["nested_repositories"]:
        print("  无")
    staged_exclusions = [r for r in report["files"] if r["decision"] == "exclude" and r["status"][0] not in {" ", "?"}]
    if staged_exclusions:
        print(f"\n警告：{len(staged_exclusions)} 个应排除项已经暂存！脚本不会修改暂存区。")
    staged_outside = [r for r in report["files"] if r["decision"] in {"outside_window", "time_unknown"} and r["status"][0] not in {" ", "?"}]
    if staged_outside:
        print(f"\n警告：{len(staged_outside)} 个范围外或时间待确认的变化已经暂存，禁止直接提交！脚本不会修改暂存区。")
    if any("U" in r["status"] or r["status"] in {"AA", "DD"} for r in report["files"]):
        print("\n警告：存在未解决冲突，禁止提交！")
    if report["snapshot_changed"]:
        print("\n警告：扫描期间 Git 状态/HEAD 变化，本次结果可能不完整，请重新运行。")
    if stats["errors"]:
        print(f"\n警告：{len(stats['errors'])} 个路径扫描失败（详见 JSON 报告），不能认定检查完整。")
    print("\n边界说明：")
    for limitation in report["limitations"]:
        print("- " + limitation)
    print("\n只读检查完成：未暂存、未提交、未推送、未修改忽略规则。")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1], help="仓库目录，默认脚本所在仓库")
    parser.add_argument("--limit", type=int, default=20, help="每类最多显示条数；0 表示全部，默认 20")
    parser.add_argument("--all", action="store_true", help="在终端显示全部路径")
    parser.add_argument("--json", type=Path, metavar="PATH", help="保存完整 JSON 报告（无凭据正文，建议写到仓库外）")
    parser.add_argument("--max-mib", type=int, default=8, help="每份内容的最大扫描大小 MiB，默认 8")
    args = parser.parse_args(argv)
    if args.limit < 0 or args.max_mib <= 0:
        parser.error("--limit 不能为负数，--max-mib 必须大于 0")
    try:
        report = audit(args.repo, args.max_mib * 1024 * 1024)
        print_report(report, 0 if args.all else args.limit)
        if args.json:
            # 用 x 模式防止覆盖用户文件；脚本默认不会生成任何文件。
            with args.json.open("x", encoding="utf-8", errors="backslashreplace") as stream:
                json.dump(report, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
            print(f"完整报告：{args.json}")
        return 0
    except (AuditError, OSError) as exc:
        print(f"检查失败：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
