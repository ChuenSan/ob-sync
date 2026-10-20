"""所有 Git 操作都在临时测试仓库中执行，不操作项目仓库。"""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "pending_commit_audit.py"
SPEC = importlib.util.spec_from_file_location("pending_commit_audit", SCRIPT)
audit_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit_module)


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.repo = Path(self.temporary.name) / "repo"
        self.repo.mkdir()
        self.command("init", "-q")
        self.command("config", "user.name", "Audit Test")
        self.command("config", "user.email", "audit@example.invalid")
        self.command("config", "commit.gpgsign", "false")
        self.command("config", "core.autocrlf", "false")

    def command(self, *args, repo=None):
        return subprocess.check_output(["git", "-C", str(repo or self.repo), *args], stderr=subprocess.PIPE)

    def put(self, path, data="普通笔记\n"):
        file = self.repo / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(data.encode() if isinstance(data, str) else data)
        return file

    def commit(self, *paths):
        self.command("add", "--", *paths)
        self.command("commit", "-qm", "test fixture")

    def baseline(self):
        self.put("tracked.md")
        self.commit("tracked.md")

    def report(self, maximum=1024 * 1024):
        return audit_module.audit(self.repo, maximum)

    def rows(self, maximum=1024 * 1024):
        return {r["path"]: r for r in self.report(maximum)["files"]}

    def test_parse_status_rename_and_unusual_filename(self):
        parsed = audit_module.parse_status(b"R  new name.md\0old name.md\0?? line\nbreak.md\0")
        self.assertEqual(parsed["new name.md"]["original_path"], "old name.md")
        self.assertEqual(parsed["line\nbreak.md"]["status"], "??")

    def test_unborn_repository(self):
        self.put("first.md")
        report = self.report()
        self.assertIsNone(report["commit_time"])
        self.assertEqual(report["git_change_count"], 1)
        self.assertEqual(report["files"][0]["decision"], "candidate")

    def test_old_untracked_file_is_outside_window_and_not_scanned(self):
        self.baseline()
        file = self.put("older.md", "-----BEGIN " + "PRIVATE KEY-----\nnot-real\n")
        os.utime(file, (1, 1))
        with mock.patch.object(audit_module.BirthTime, "get", return_value=1.0):
            row = self.rows()["older.md"]
        self.assertEqual(row["decision"], "outside_window")
        self.assertEqual(row["scanned_sources"], [])
        self.assertEqual(row["findings"], [])

    def test_new_file_with_old_mtime_uses_recent_birth(self):
        self.baseline()
        file = self.put("new.md")
        os.utime(file, (1, 1))
        with mock.patch.object(audit_module.BirthTime, "get", return_value=audit_module.time.time()):
            row = self.rows()["new.md"]
        self.assertEqual(row["decision"], "candidate")

    def test_old_untracked_file_recently_modified_is_current(self):
        self.baseline()
        self.put("changed.md", "recent edit\n")
        with mock.patch.object(audit_module.BirthTime, "get", return_value=1.0):
            row = self.rows()["changed.md"]
        self.assertEqual(row["decision"], "candidate")

    def test_unknown_birth_and_old_mtime_need_time_confirmation(self):
        self.baseline()
        file = self.put("unknown.md")
        os.utime(file, (1, 1))
        with mock.patch.object(audit_module.BirthTime, "get", return_value=None):
            row = self.rows()["unknown.md"]
        self.assertEqual(row["decision"], "time_unknown")
        self.assertEqual(row["scanned_sources"], [])

    def test_staged_historical_file_blocks_direct_commit(self):
        self.baseline()
        file = self.put("older.md")
        self.command("add", "--", "older.md")
        os.utime(file, (1, 1))
        with mock.patch.object(audit_module.BirthTime, "get", return_value=1.0):
            report = self.report()
        row = next(r for r in report["files"] if r["path"] == "older.md")
        self.assertEqual(row["decision"], "outside_window")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            audit_module.print_report(report, 20)
        self.assertIn("禁止直接提交", output.getvalue())
        self.assertIn(b"older.md", self.command("diff", "--cached", "--name-only"))

    def test_old_tracked_modification_not_rescued_by_recent_birth(self):
        self.baseline()
        file = self.put("tracked.md", "old change\n")
        os.utime(file, (1, 1))
        row = self.rows()["tracked.md"]
        self.assertEqual(row["decision"], "outside_window")

    def test_unchanged_tracked_file_with_recent_mtime(self):
        self.baseline()
        os.utime(self.repo / "tracked.md", None)
        row = self.rows()["tracked.md"]
        self.assertEqual(row["decision"], "unchanged")
        self.assertEqual(row["findings"], [])

    def test_secret_in_staging_but_not_worktree(self):
        self.baseline()
        secret = "sk-" + "Q" * 32
        self.put("note.md", "api_key = '" + secret + "'\n")
        self.command("add", "--", "note.md")
        self.put("note.md", "无凭据的工作区版本\n")
        report = self.report()
        row = next(r for r in report["files"] if r["path"] == "note.md")
        self.assertEqual(row["decision"], "review")
        self.assertTrue(any(f["source"] == "暂存区" for f in row["findings"]))
        self.assertNotIn(secret, json.dumps(report))
        self.assertTrue(report["diffs"]["staged"]["has_diff"])
        self.assertTrue(report["diffs"]["unstaged"]["has_diff"])

    def test_private_key_is_excluded(self):
        self.baseline()
        self.put("private.pem", "-----BEGIN " + "PRIVATE KEY-----\nnot-a-real-key\n")
        row = self.rows()["private.pem"]
        self.assertEqual(row["decision"], "exclude")
        self.assertTrue(row["findings"])

    def test_staged_private_key_removed_from_worktree_still_excluded(self):
        self.baseline()
        self.put("key.txt", "-----BEGIN " + "RSA PRIVATE KEY-----\nnot-a-real-key\n")
        self.command("add", "--", "key.txt")
        self.put("key.txt", "safe\n")
        self.assertEqual(self.rows()["key.txt"]["decision"], "exclude")

    def test_ignored_recent_file_is_excluded(self):
        self.baseline()
        self.put(".gitignore", "ignored.md\n")
        self.put("ignored.md")
        row = self.rows()["ignored.md"]
        self.assertEqual(row["decision"], "exclude")
        self.assertIn("被 Git 忽略规则排除", row["reasons"])

    def test_metadata_and_local_config_are_excluded(self):
        self.baseline()
        self.put("._note.md", b"metadata")
        self.put(".obsidian/settings.json", "{}")
        self.put(".env", "example=not-real\n")
        rows = self.rows()
        for path in ("._note.md", ".obsidian/settings.json", ".env"):
            self.assertEqual(rows[path]["decision"], "exclude", path)

    def test_changes_in_pruned_directory_are_still_checked(self):
        self.put("build/file.txt")
        self.commit("build/file.txt")
        self.put("build/file.txt", "modified\n")
        row = self.rows()["build/file.txt"]
        self.assertIn("Git 状态", row["sources"])
        self.assertEqual(row["decision"], "exclude")

    def test_empty_documents_and_export_markers(self):
        self.baseline()
        self.put("empty.md", "")
        self.put("notes/.export", "")
        rows = self.rows()
        self.assertEqual(rows["empty.md"]["decision"], "review")
        self.assertEqual(rows["notes/.export"]["decision"], "exclude")

    def test_binary_header_is_not_mistaken_for_plain_text(self):
        findings, concerns = audit_module.inspect_bytes(b"%PDF-1.4\nASCII PDF", "工作区")
        self.assertEqual(findings, [])
        self.assertTrue(concerns)

    def test_staged_exclusion_is_reported_but_not_unstaged(self):
        self.baseline()
        self.put(".env")
        self.command("add", "--", ".env")
        before = self.command("diff", "--cached", "--name-only")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            audit_module.print_report(self.report(), 20)
        self.assertIn("应排除项已经暂存", output.getvalue())
        self.assertEqual(before, self.command("diff", "--cached", "--name-only"))

    def test_staged_delete_requires_time_confirmation(self):
        self.baseline()
        self.command("rm", "--", "tracked.md")
        row = self.rows()["tracked.md"]
        self.assertEqual(row["decision"], "time_unknown")
        self.assertEqual(row["scanned_sources"], [])

    def test_rename_preserves_original_path(self):
        self.baseline()
        self.command("mv", "--", "tracked.md", "renamed.md")
        row = self.rows()["renamed.md"]
        self.assertEqual(row["decision"], "time_unknown")
        self.assertEqual(row["original_path"], "tracked.md")

    def test_binary_and_large_files_require_review(self):
        self.baseline()
        self.put("image.bin", b"\0\1\2")
        self.put("large.txt", "a" * 100)
        rows = self.rows(maximum=50)
        self.assertEqual(rows["image.bin"]["decision"], "review")
        self.assertEqual(rows["large.txt"]["decision"], "review")

    @unittest.skipUnless(hasattr(os, "symlink"), "requires symlink support")
    def test_symlink_target_is_not_read(self):
        self.baseline()
        external = Path(self.temporary.name) / "secret"
        external.write_text("-----BEGIN " + "PRIVATE KEY-----\nnot-real\n")
        try:
            (self.repo / "link.md").symlink_to(external)
        except OSError:
            self.skipTest("symlink creation not permitted")
        row = self.rows()["link.md"]
        self.assertEqual(row["decision"], "review")
        self.assertEqual(row["findings"], [])

    @unittest.skipUnless(hasattr(os, "symlink"), "requires symlink support")
    def test_symlink_parent_does_not_expose_external_file(self):
        self.put("docs/note.md")
        self.commit("docs/note.md")
        external = Path(self.temporary.name) / "external"
        external.mkdir()
        (external / "note.md").write_text("-----BEGIN " + "PRIVATE KEY-----\nnot-real\n")
        (self.repo / "docs").rename(Path(self.temporary.name) / "old-docs")
        try:
            (self.repo / "docs").symlink_to(external, target_is_directory=True)
        except OSError:
            self.skipTest("symlink creation not permitted")
        row = self.rows()["docs/note.md"]
        self.assertEqual(row["decision"], "time_unknown")
        self.assertEqual(row["findings"], [])

    def test_remote_credentials_and_query_are_redacted(self):
        self.baseline()
        url = "https://" + "testuser:" + "not-real-pass@" + "example.invalid/repo?token=" + "not-real-token"
        self.command("remote", "add", "origin", url)
        report = self.report()
        self.assertNotIn("not-real-pass", report["remotes"])
        self.assertNotIn("not-real-token", report["remotes"])

    def test_nested_repository_is_separate(self):
        self.baseline()
        nested = self.repo / "nested"
        nested.mkdir()
        self.command("init", "-q", repo=nested)
        (nested / "inside.md").write_text("nested note\n")
        report = self.report()
        row = next(r for r in report["files"] if r["path"] == "nested")
        self.assertEqual(row["decision"], "time_unknown")
        self.assertEqual(report["nested_repositories"][0]["changes"][0]["path"], "inside.md")
        self.assertFalse(any(r["path"].startswith("nested/") for r in report["files"]))

    def test_read_only_and_status_unchanged(self):
        self.baseline()
        self.put("new.md")
        before_status = self.command("status", "--porcelain=v1", "-z", "--untracked-files=all")
        before_files = sorted(p.relative_to(self.repo).as_posix() for p in self.repo.rglob("*") if ".git" not in p.relative_to(self.repo).parts)
        report = self.report()
        self.assertFalse(report["snapshot_changed"])
        self.assertEqual(before_status, self.command("status", "--porcelain=v1", "-z", "--untracked-files=all"))
        self.assertEqual(before_files, sorted(p.relative_to(self.repo).as_posix() for p in self.repo.rglob("*") if ".git" not in p.relative_to(self.repo).parts))

    def test_birthtime_native_and_missing(self):
        class Native:
            st_birthtime = 123.5
        class Missing:
            pass
        birth = audit_module.BirthTime()
        self.assertEqual(birth.get(self.repo, Native()), 123.5)
        birth.statx = None
        self.assertIsNone(birth.get(self.repo, Missing()))

    def test_conflict_blocks_classification(self):
        self.put("conflict.md")
        row = audit_module.inspect_entry(
            self.repo, "conflict.md", {"status": "UU"}, None, False,
            set(), audit_module.BirthTime(), 100,
        )
        self.assertEqual(row["decision"], "review")
        self.assertTrue(any("冲突" in r for r in row["reasons"]))

    def test_control_characters_in_paths_are_escaped(self):
        escaped = audit_module.display_path("bad\nname.md")
        self.assertNotIn("\n", escaped)
        self.assertIn("\\n", escaped)

    def test_existing_json_report_is_not_overwritten(self):
        self.baseline()
        output = Path(self.temporary.name) / "report.json"
        output.write_text("preserve")
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            code = audit_module.main(["--repo", str(self.repo), "--json", str(output)])
        self.assertEqual(code, 2)
        self.assertEqual(output.read_text(), "preserve")


if __name__ == "__main__":
    unittest.main()
