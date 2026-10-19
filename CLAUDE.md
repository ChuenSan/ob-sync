# CLAUDE.md

## GitHub 文件同步、提交与推送规则

本文件规定 Claude 在项目中执行 Git 文件检查、Commit、远程同步、冲突处理及 Push 时必须遵循的规则。

**核心原则：时间定位变化，Git 验证状态，Claude 判断内容。确保不遗漏真实修改，同时避免提交无关、临时或敏感文件。**

## 1. 文件变更识别

### 1.1 时间判断

使用以下时间变量：

- `T_commit`：本地 HEAD Commit 的 **Committer Date**，不使用 Author Date。
    
- `T_now`：执行任务时的 macOS 当前系统时间。
    
- `T_file_mtime`：文件最后修改时间。
    
- `T_file_birth`：文件在当前文件系统中的创建时间（Birth Time）。
    

获取时间：

```
git log -1 --format=%cI HEAD
date +"%Y-%m-%dT%H:%M:%S%z"

# 文件修改时间
stat -f "%Sm" -t "%Y-%m-%dT%H:%M:%S%z" "文件路径"

# 文件创建时间
stat -f "%SB" -t "%Y-%m-%dT%H:%M:%S%z" "文件路径"
```

时间判断条件：

```
修改文件：T_commit < T_file_mtime <= T_now
新增文件：T_commit < T_file_birth <= T_now
```

比较时必须包含完整日期、时间和时区。

默认认为 mtime 变化代表真实内容修改，Birth Time 可辅助判断新增文件。除非有明确异常证据，否则不主动考虑 touch、人为修改时间戳或特殊文件系统行为。

### 1.2 Git 状态兜底

时间筛选不能替代 Git 检查。每次 Commit 前必须执行：

```
git status --porcelain
git diff
git diff --cached
```

检查所有新增、修改、删除、重命名、移动、未跟踪、已暂存、未暂存及冲突文件。

最终候选范围：

```
CandidateFiles = TimeBasedFiles ∪ GitChangedFiles
```

即使文件时间不在窗口内，只要 Git 检测到未提交变化，也必须检查，不得直接忽略。

删除文件主要通过 Git 状态和 diff 判断；重命名、移动需结合 Git 的 rename 或 delete + add 结果判断。

### 1.3 最终提交判断

Claude 必须综合：

- 时间候选文件及 Git 检测到的变化；
    
- 当前任务、项目结构、文件用途；
    
- 文件内容、Git diff、`.gitignore`。
    

排除 `.git/`、缓存、依赖、构建产物、日志、临时文件、IDE 文件、无关文件，以及密码、API Key、Token、私钥、Cookie、证书私钥、数据库凭据、`.env`、本地配置和个人敏感信息。

**宁可多检查，也不能漏掉真实修改；但多检查不等于全部提交。**

## 2. 标准 Commit 流程

### 第一步：确认仓库

```
git rev-parse --show-toplevel
git branch --show-current
git remote -v
```

确认目标仓库、当前分支和远程地址正确。

### 第二步：确定候选文件

1. 获取 `T_commit` 和 `T_now`。
    
2. 扫描项目文件的 mtime、Birth Time，排除 `.git/` 及无需扫描的缓存、依赖、构建目录。
    
3. 根据时间窗口生成候选文件。
    
4. 通过 `git status --porcelain`、`git diff`、`git diff --cached` 补充所有 Git 变化。
    
5. Claude 检查实际内容并确定最终提交范围。
    

### 第三步：检查与暂存

Commit 前确认：

- 修改正确，没有遗漏或意外删除。
    
- 没有无关文件、临时文件或敏感信息。
    
- 没有未解决冲突。
    
- 已暂存与未暂存的变化均经过检查。
    

优先明确指定文件：

```
git add path/to/file1 path/to/file2
```

禁止未经检查直接执行 `git add .`。仅在确认所有变化均应提交时，才可使用 `git add -A`。

### 第四步：提交

```
git diff --cached
git commit -m "清晰描述本次修改"
```

Commit Message 应说明实际修改内容，避免使用 `update`、`test` 等模糊描述。

## 3. Push 前同步远程

每次 Push 前必须获取远程最新状态：

```
git fetch --prune
git status -sb
git rev-list --left-right --count HEAD...@{u}
```

后两个命令适用于已配置 upstream 的分支。

根据检查结果：

- **远程没有新提交**：可以进入最终 Push 检查。
    
- **远程存在新提交**：必须先同步，不得直接覆盖远程。
    
- **本地与远程分叉**：先同步、解决冲突并验证，再 Push。
    

个人开发分支优先：

```
git pull --rebase
```

以保持提交历史线性；如果项目规定 Merge 工作流，则遵循现有规范。

### 冲突处理

同步发生冲突时，必须停止自动 Push。

1. 执行 `git status` 检查冲突文件。
    
2. 综合本地版本、远程版本、当前任务及项目逻辑分析冲突。
    
3. 不得无条件选择 `ours` 或 `theirs` 覆盖另一方。
    
4. 解决冲突后执行：
    

```
git add <resolved-files>
git rebase --continue
```

继续处理剩余冲突，直到 Rebase 完成。

无法安全解决时，可执行：

```
git rebase --abort
```

恢复 Rebase 前的状态并重新分析。

**冲突未完全解决、文件未检查或同步结果未验证时，禁止 Push。**

## 4. Push 与验证

### Push 前检查

```
git status
git log --oneline --decorate -n 5
git diff @{u}..HEAD
```

确认工作区状态、待推送 Commit 和实际变更内容。最后一个命令适用于存在 upstream 的情况。

确认无误后执行：

```
git push
```

首次推送且没有 upstream 时，在确认目标正确后执行：

```
git push -u origin <branch>
```

### Push 后验证

执行：

```
git status
```

确认：

- Push 成功，远程分支已包含本次 Commit。
    
- 远程最新代码已同步。
    
- 不存在未解决冲突。
    
- 没有因时间筛选遗漏应提交的文件。
    
- 工作区干净，或剩余未提交变化已明确识别。
    

如果仍有未提交文件，必须说明文件名称、未提交原因及是否需要后续处理。不得在存在未知变化时宣称全部完成。

## 5. 高风险操作限制

除非用户明确要求，否则禁止自动执行：

```
git reset --hard
git clean -fd
git push --force
git checkout -- .
git restore .
```

同样禁止擅自删除远程修改、覆盖他人代码、丢弃本地修改、重置整个仓库或执行其他可能导致文件、Commit、远程历史丢失的操作。

默认禁止 Force Push。只有用户明确要求且已确认风险与范围时，才可考虑 `git push --force-with-lease`，优先于 `--force`。

执行 Rebase、Merge、Checkout、Restore、Reset 等可能影响工作区的操作前，必须先执行 `git status`，保护未提交内容。

## 6. 特殊情况处理

### 6.1 仓库没有 Commit

若 HEAD 不存在，则 `T_commit` 不存在，不得使用 Commit 时间窗口。

首次 Commit 应检查所有合理项目文件、Git 未跟踪文件及已暂存文件。首次提交完成后，再使用正常时间规则。

### 6.2 没有远程仓库

若 `git remote -v` 没有结果，不得擅自创建未知 Remote。必须先确认目标地址，再配置远程仓库。

### 6.3 没有 Upstream

确认远程目标后，使用：

```
git push -u origin <branch>
```

### 6.4 存在较早的未提交修改

即使文件 `mtime < T_commit`，只要 Git 显示 modified、untracked、deleted 或 renamed，Claude 仍必须检查其内容，决定是否提交。

### 6.5 Git 操作改变文件时间

`git pull`、`checkout`、`rebase`、`merge` 可能改变本地文件 mtime。

此时以 Git 状态为主要依据。若 Git 确认文件没有未提交变化，不应仅因 mtime 改变而生成新 Commit。

从 GitHub 拉取的已有内容不需要重复 Commit 或 Push，只有本地新增变化才需要新提交。

### 6.6 推送后的时间基准

下一次同步必须重新获取：

```
git log -1 --format=%cI HEAD
```

使用最新本地 HEAD 的 Committer Date，不得长期缓存旧的 `T_commit`。

## 7. 完整执行流程

```
确认 Git 仓库、Branch、Remote
             ↓
读取 HEAD Committer Date
             ↓
获取 macOS 当前系统时间
             ↓
扫描文件 mtime / Birth Time
             ↓
获取 Git status / diff
             ↓
合并所有候选文件
             ↓
Claude 检查内容、用途及任务
             ↓
排除无关、忽略、临时、敏感文件
             ↓
检查最终提交范围
             ↓
git add 指定文件
             ↓
git diff --cached
             ↓
git commit
             ↓
git fetch --prune
             ↓
检查本地与远程关系
             ↓
       远程有新提交？
         /       \
        是        否
        ↓         │
   rebase / merge │
        ↓         │
   解决冲突并验证 │
        └────┬────┘
             ↓
    最终状态和 Commit 检查
             ↓
          git push
             ↓
      验证远程推送成功
             ↓
    说明剩余未提交变化
             ↓
            完成
```

## 8. 最终执行原则

1. 时间窗口用于发现变化，Git 状态用于防止遗漏。
    
2. Claude 根据实际 diff、文件用途和任务上下文决定提交范围。
    
3. 不因时间窗口遗漏旧修改，也不因时间戳变化盲目提交。
    
4. Commit 前检查内容、敏感信息及暂存范围。
    
5. Push 前必须检查并同步远程最新提交。
    
6. 冲突必须妥善解决，不得粗暴覆盖任一版本。
    
7. 禁止未经授权的破坏性操作和 Force Push。
    
8. Push 后必须确认远程结果及剩余未提交变化。
    

**最终成功标准：所有应提交的修改均已正确 Commit，远程最新代码已同步，冲突全部解决，Push 成功且远程包含本次提交，不存在因时间判断或 Git 状态检查不足而遗漏的合理修改。**