# CLAUDE.md

## GitHub 文件同步、提交与推送规则

本文档用于规定 Claude 在本项目中处理本地文件变更、Git Commit、远程同步、冲突处理以及 GitHub Push 时必须遵循的逻辑。



本项目不单纯依赖 Git 自动决定提交范围.



Claude 需要综合以下信息判断本次需要提交和推送的文件：

1. 本地最近一次 Commit 的时间；
2. macOS 文件系统中的文件修改时间；
3. macOS 文件系统中的文件创建时间；
4. Git 当前工作区状态；
5. 当前任务实际涉及的文件；
6. 远程仓库的最新状态.



最终目标是：

> 尽可能保证所有真实发生过修改、新增、删除或重命名的文件都不会遗漏，同时避免将与当前项目无关的文件、临时文件或敏感文件错误提交到 GitHub。





---

# 1. 核心原则

Claude 执行 Git 操作时必须遵循以下原则.



## 1.1 不遗漏真实修改

凡是在本地实际发生过以下变化的文件，都应进入检查范围：

- 新增；
- 修改；
- 删除；
- 重命名；
- 移动；
- 冲突解决后产生的修改.



不得仅因为某个文件没有出现在主要时间窗口内，就直接忽略 Git 已经检测到的未提交变化.



---

## 1.2 时间是主要判断依据

本项目使用：

- 本地 HEAD Commit 的 `Committer Date`
- 文件 `mtime`
- 文件 `Birth Time`
- 当前 macOS 系统时间



建立文件变化的主要判断窗口.



---

## 1.3 Git 状态作为兜底

时间判断用于寻找主要候选文件。Git 状态用于防止：

- 文件遗漏；
- 删除文件遗漏；
- 重命名遗漏；
- 时间戳异常导致的遗漏；
- 其它 Git 已经识别、但时间筛选没有识别的变化.



因此：

```text
最终候选文件
=
时间窗口识别出的文件
+
Git 检测到的所有未提交变化
```



---

## 1.4 最终由 Claude 判断

时间和 Git 状态都只是信息来源.



最终是否提交某个文件，由 Claude 根据：

- 当前任务；
- 文件内容；
- Git diff；
- 项目结构；
- `.gitignore`；
- 文件用途；

综合判断.



---

## 1.5 禁止盲目提交

不得仅因为文件发生变化，就无条件执行：

```bash
git add .
```



在加入暂存区之前，Claude 必须确认文件确实属于本项目并适合提交.



---

# 2. 时间定义

本项目统一使用以下几个时间变量.



```text
T_commit
    最近一次本地 HEAD Commit 的 Committer Date

T_now
    本次执行 Git 推送任务时的当前 macOS 系统时间

T_file_mtime
    文件最后修改时间

T_file_birth
    文件 Birth Time / Creation Time
```



---

# 3. Commit 时间定义

本文所说的：

> 本地 Commit 时间

统一指：

```text
当前本地 HEAD Commit 的 Committer Date
```

而不是：

```text
Author Date
```

也不是：

```text
GitHub 页面显示的时间
```

也不是远程服务器时间.



---

## 3.1 获取 Committer Date

使用：

```bash
git log -1 --format=%cI HEAD
```

例如：

```text
2026-09-02T10:52:31+08:00
```

将该时间记录为：

```text
T_commit
```

---

## 3.2 为什么使用 Committer Date

Git Commit 中可能同时存在：

```text
Author Date
Committer Date
```

例如经过：

```bash
git commit --amend
git rebase
git cherry-pick
```

之后，两者可能不同.



本项目不使用 `Author Date`.



统一使用：

```text
Committer Date
```

作为本地 Commit 时间基准.



---

# 4. 当前系统时间

执行本次同步任务时，获取当前 macOS 系统时间.



例如：

```bash
date +"%Y-%m-%dT%H:%M:%S%z"
```

记录为：

```text
T_now
```

判断时必须使用：

```text
完整日期
+
时间
+
时区
```

不得只比较：

```text
小时
分钟
秒
```

---

# 5. 文件变更识别原则

## 5.1 修改文件

对于已经存在的文件，以：

```text
mtime
```

作为最后修改时间.



如果满足：

```text
T_commit < T_file_mtime <= T_now
```

则该文件进入本次推送候选范围.



---

## 5.2 新增文件

对于新增文件，以 macOS 文件系统提供的：

```text
Birth Time
```

作为当前工作目录中该文件的创建时间.



如果满足：

```text
T_commit < T_file_birth <= T_now
```

则该文件进入本次推送候选范围.



---

# 6. macOS 文件时间

本项目运行环境为：

```text
macOS
```

因此可以利用 macOS/APFS 提供的文件时间信息.



---

## 6.1 查看文件修改时间

例如：

```bash
stat -f "%Sm" -t "%Y-%m-%dT%H:%M:%S%z" "文件路径"
```

---

## 6.2 查看文件 Birth Time

例如：

```bash
stat -f "%SB" -t "%Y-%m-%dT%H:%M:%S%z" "文件路径"
```

---

## 6.3 时间含义

本文约定：

```text
Birth Time
    文件在当前文件系统中的创建时间

mtime
    文件内容最后一次修改时间
```



---

# 7. 文件时间判断假设

本项目默认采用以下业务假设：

## 7.1 mtime

默认认为：

> 文件 mtime 发生变化，代表文件内容发生了真实修改.除非发现明确异常，否则不主动考虑：

- `touch`；
- 人为修改时间戳；
- 特殊同步软件修改时间；
- 文件系统异常；
- 第三方程序错误维护时间戳；

等极端情况.



---

## 7.2 Birth Time

默认认为：

> macOS Birth Time 可以表示文件在当前工作目录中的创建时间.

对于当前项目的推送判断，可以使用 Birth Time 辅助判断新增文件.



---

## 7.3 Git 最终校验

即使采用上述假设，在正式 Commit 前仍然必须使用 Git 状态进行最终校验.



---

# 8. Git 状态兜底

每次 Commit 前必须执行：

```bash
git status --porcelain
```

并根据需要执行：

```bash
git status
git diff
git diff --cached
```



---

## 8.1 必须检查的 Git 状态

包括：

```text
新增
修改
删除
重命名
移动
未跟踪文件
已暂存文件
未暂存文件
冲突文件
```

例如：

```text
 M README.md
 M src/main.py
 D old-file.md
?? new-file.md
```

都必须进入 Claude 的检查范围.



---

# 9. 最终候选文件计算方式

最终候选文件集合定义为：

```text
CandidateFiles
=
TimeBasedFiles
∪
GitChangedFiles
```

其中：

```text
TimeBasedFiles
=
满足时间条件的新增或修改文件
```

```text
GitChangedFiles
=
Git 当前检测到的所有未提交变化
```

即：

```text
时间范围检测
        +
git status
        +
git diff
        ↓
Claude 综合判断
        ↓
最终提交文件
```



---

# 10. 删除文件处理

删除文件已经不存在，因此：

```text
mtime
Birth Time
```

无法作为主要判断依据.删除文件必须通过 Git 判断：

```bash
git status --porcelain
```

以及：

```bash
git diff
```

如果确认删除属于本次工作内容，则必须纳入 Commit.



---

# 11. 重命名与移动文件

文件重命名或移动时，不单纯依赖：

```text
Birth Time
mtime
```

判断.优先结合：

```bash
git status
git diff
```

判断 Git 是否识别为：

```text
rename
```

或者：

```text
delete + add
```

最终根据实际文件内容决定是否提交.



---

# 12. 忽略文件

时间范围扫描不得绕过：

```text
.gitignore
```

对于已经被 Git 正确忽略的：

```text
缓存
构建产物
日志
临时文件
依赖目录
IDE 文件
```

通常不得加入本次提交.



---

# 13. 敏感文件检查

Commit 前必须检查是否存在：

```text
密码
API Key
Token
Private Key
Cookie
证书私钥
数据库凭据
.env
本地配置
个人信息
```

除非项目明确要求，否则禁止将敏感内容提交到 GitHub.



---

# 14. 推送总体流程

每次执行 GitHub 推送任务时，按照以下流程操作：

```text
确认 Git 仓库
      ↓
确认当前 Branch
      ↓
确认远程仓库
      ↓
获取本地 HEAD Committer Date
      ↓
记录 T_commit
      ↓
获取当前系统时间
      ↓
记录 T_now
      ↓
扫描文件 mtime / Birth Time
      ↓
得到时间候选文件
      ↓
git status
      ↓
git diff
      ↓
补充 Git 检测到的变化
      ↓
Claude 检查文件内容
      ↓
确定最终提交文件
      ↓
本地 Commit
      ↓
获取远程仓库最新状态
      ↓
检查远程是否存在新提交
      ↓
同步远程
      ↓
检查冲突
   ↙        ↘
有冲突      无冲突
  ↓           ↓
解决冲突      │
  ↓           │
重新检查       │
  └─────┬─────┘
        ↓
最终状态检查
        ↓
Push
        ↓
确认远程 Push 成功
```



---

# 15. 第一步：确认仓库状态

执行：

```bash
git rev-parse --show-toplevel
```

确认当前目录属于目标 Git 仓库.然后执行：

```bash
git branch --show-current
```

确认当前 Branch.再检查：

```bash
git remote -v
```

确认远程仓库地址.



---

# 16. 第二步：确定时间窗口

执行：

```bash
git log -1 --format=%cI HEAD
```

获得：

```text
T_commit
```

然后获取：

```text
T_now
```

最终形成：

```text
T_commit
    <
文件变化时间
    <=
T_now
```

例如：

```text
2026-09-01T18:30:00+08:00
<
文件修改时间
<=
2026-09-02T11:30:00+08:00
```



---

# 17. 第三步：扫描本地文件

检查：

```text
mtime
Birth Time
```

并建立时间候选文件列表.必须排除：

```text
.git/
```

以及明确不应该扫描的缓存、依赖、构建目录.



---

# 18. 第四步：Git 状态验证

执行：

```bash
git status --porcelain
```

必要时执行：

```bash
git diff
```

和：

```bash
git diff --cached
```

将 Git 检测到的：

```text
新增
修改
删除
重命名
```

等变化加入检查范围.



---

# 19. 第五步：Claude 判断本次提交内容

Claude 必须查看：

```text
时间候选文件
+
Git 变化文件
+
当前任务内容
```

然后确定：

```text
最终需要提交的文件
```

判断原则：

> 宁可多检查一个文件，也不要因为单纯的时间筛选而漏掉真实未提交修改.



但是：

> 多检查不等于无条件提交.



---

# 20. 第六步：Commit 前检查

Commit 前必须再次检查：

```bash
git status
```

以及：

```bash
git diff
```

确认：

1. 修改内容正确；
2. 没有无关文件；
3. 没有敏感信息；
4. 没有意外删除；
5. 没有未解决冲突；
6. 没有不应提交的临时文件.



---

# 21. 暂存规则

优先明确指定文件：

```bash
git add path/to/file1 path/to/file2
```

而不是直接：

```bash
git add .
```

如果确实需要提交当前全部合理变化，则可以使用：

```bash
git add -A
```

但必须在执行之前完成状态检查.



---

# 22. 本地 Commit

确认暂存内容：

```bash
git diff --cached
```

确认无误后执行：

```bash
git commit -m "清晰描述本次修改"
```

Commit Message 应尽量描述：

```text
做了什么
```

而不是：

```text
update
修改
test
```

等无意义信息.



---

# 23. Push 前必须同步远程仓库

每次 Push 到 GitHub 前，都必须获取远程仓库最新状态.

首先：

```bash
git fetch --prune
```

然后检查本地与远程关系.如果当前分支存在 upstream，可以检查：

```bash
git status -sb
```

必要时：

```bash
git rev-list --left-right --count HEAD...@{u}
```



---

# 24. 远程没有新提交

如果确认：

```text
本地 HEAD
=
远程最新提交
+
本地自己的 Commit
```

即不存在需要先合并的远程变化，可以继续 Push.



---

# 25. 远程存在新提交

如果发现远程仓库在本地工作期间产生了新的 Commit：

必须先同步.



优先：

```bash
git pull --rebase
```

或者根据当前仓库已有工作流决定使用：

```bash
git merge
```



---

# 26. 为什么优先 Rebase

对于个人开发分支，优先：

```bash
git pull --rebase
```

可以让提交历史更加线性.



例如：

```text
远程：
A → B → C

本地：
A → B → D
```

Rebase 后：

```text
A → B → C → D'
```

避免不必要的 Merge Commit.



但是如果项目明确要求 Merge 工作流，应遵循项目现有规范.



---

# 27. 冲突处理

如果：

```bash
git pull --rebase
```

或其它同步操作发生冲突：

立即停止自动 Push.



---

## 27.1 检查冲突

执行：

```bash
git status
```

确认冲突文件.



---

## 27.2 Claude 处理冲突

Claude 必须综合：

```text
本地版本
远程版本
当前任务
项目逻辑
```

分析冲突.



不得无条件选择：

```text
ours
```

或：

```text
theirs
```

覆盖另一侧.



---

## 27.3 冲突解决完成

如果正在进行 Rebase：

```bash
git add <resolved-files>
git rebase --continue
```

如果还有冲突：

继续解决.



直到 Rebase 完成.



---

## 27.4 放弃错误 Rebase

如果确认无法安全解决，可以：

```bash
git rebase --abort
```

恢复 Rebase 之前的状态.



然后重新分析.



---

# 28. 禁止粗暴覆盖远程

除非用户明确要求，否则禁止：

```bash
git push --force
```

也禁止为了省事：

```text
删除远程修改
覆盖他人代码
丢弃本地修改
重置整个仓库
```



---

# 29. Force Push

默认：

```text
禁止 Force Push
```

只有用户明确要求，且 Claude 已经确认操作范围与风险时，才允许考虑：

```bash
git push --force-with-lease
```

即使需要 Force Push，也优先：

```bash
--force-with-lease
```

而不是：

```bash
--force
```



---

# 30. 最终 Push 前检查

Push 前执行：

```bash
git status
```

确认工作区状态.然后查看：

```bash
git log --oneline --decorate -n 5
```

确认即将 Push 的 Commit.必要时检查：

```bash
git diff @{u}..HEAD
```

确认本地准备推送到远程的实际内容.



---

# 31. Push

确认无误后：

```bash
git push
```

如果当前分支第一次 Push：

```bash
git push -u origin <branch>
```



---

# 32. Push 后验证

Push 成功后再次执行：

```bash
git status
```

确认类似：

```text
Your branch is up to date with 'origin/<branch>'.
```

同时确认：

```text
nothing to commit, working tree clean
```

或者明确知道剩余未提交变化是什么.



---

# 33. 拉取远程代码导致文件时间变化

如果：

```bash
git pull
```

或：

```bash
git checkout
git rebase
git merge
```

改变了本地文件 mtime：

不应仅因为时间发生变化，就认为这些内容是新的本地修改.



因为 Git 已经知道这些文件当前对应的仓库状态.所以发生远程同步以后：

> Git 状态优先用于确认内容是否真的属于新的未提交变化.如果：

```bash
git status
```

显示文件无变化，则不需要因为 mtime 改变重新创建 Commit.



---

# 34. 远程拉取内容不需要重复 Push

如果某段内容：

```text
GitHub
  ↓
git pull
  ↓
本地
```

本身已经存在于 GitHub，则不需要再次产生 Commit 或重复 Push.



只有：

```text
本地新增变化
```

才需要形成新的 Commit.



---

# 35. 特殊情况：仓库没有任何 Commit

如果执行：

```bash
git log -1
```

发现：

```text
HEAD 不存在
```

说明当前仓库尚未产生第一次 Commit.



此时：

```text
T_commit
```

不存在.



不得继续使用 Commit 时间窗口.应改为：

```text
所有合理项目文件
+
Git 未跟踪文件
+
Git 已暂存文件
```

作为第一次 Commit 的候选范围.



第一次 Commit 完成后，再开始使用正常时间窗口规则.



---

# 36. 特殊情况：没有远程仓库

如果：

```bash
git remote -v
```

没有任何结果：

Claude 不得擅自创建未知 Remote.



需要确认远程仓库地址以后，再进行：

```bash
git remote add origin ...
```



---

# 37. 特殊情况：当前分支没有 Upstream

如果：

```text
当前 Branch 尚未跟踪远程 Branch
```

在确认远程目标正确以后，可以：

```bash
git push -u origin <branch>
```

建立 upstream.



---

# 38. 特殊情况：工作区存在旧的未提交修改

即使某个文件：

```text
mtime < T_commit
```

但是：

```bash
git status
```

仍然显示：

```text
modified
untracked
deleted
renamed
```

则该文件不得直接忽略.



必须由 Claude 检查.



这也是 Git 状态兜底存在的原因.



---

# 39. 特殊情况：本地与远程发生分叉

例如：

```text
        C
       /
A → B
       \
        D
```

其中：

```text
C = 远程新提交
D = 本地新提交
```

不得直接 Force Push.



应该优先：

```text
fetch
↓
rebase / merge
↓
解决冲突
↓
测试
↓
push
```



---

# 40. 不得自动执行的高风险操作

除非用户明确要求，否则不得自动执行：

```bash
git reset --hard
```

```bash
git clean -fd
```

```bash
git push --force
```

```bash
git checkout -- .
```

```bash
git restore .
```

以及任何可能导致：

```text
本地文件永久丢失
Commit 丢失
远程历史被覆盖
```

的操作.



---

# 41. Git 操作前保护原则

如果即将执行可能改变工作区的操作，例如：

```text
rebase
merge
checkout
restore
reset
```

Claude 必须首先确认：

```bash
git status
```

确保不会意外破坏未提交内容.



---

# 42. 推送后的时间基准

Push 完成以后：

新的本地 HEAD Commit 会成为下一次同步任务的：

```text
T_commit
```

下一次运行时重新执行：

```bash
git log -1 --format=%cI HEAD
```

获取新的时间基准.



不得长期缓存旧的：

```text
T_commit
```



---

# 43. 最终完整执行流程

```text
开始
 │
 ▼
确认当前 Git 仓库
 │
 ▼
确认 Branch / Remote
 │
 ▼
读取本地 HEAD Committer Date
 │
 ├── 无 Commit
 │      ↓
 │   第一次 Commit 特殊流程
 │
 ▼
记录 T_commit
 │
 ▼
读取 macOS 当前时间
 │
 ▼
记录 T_now
 │
 ▼
扫描文件
 │
 ├── mtime
 │
 └── Birth Time
 │
 ▼
生成时间候选文件
 │
 ▼
git status --porcelain
 │
 ▼
git diff
 │
 ▼
补充：
新增 / 修改 / 删除 / 重命名
 │
 ▼
Claude 综合判断
 │
 ▼
排除：
.gitignore
临时文件
敏感文件
无关文件
 │
 ▼
确认最终提交文件
 │
 ▼
git add 指定文件
 │
 ▼
git diff --cached
 │
 ▼
Commit
 │
 ▼
git fetch --prune
 │
 ▼
检查远程是否更新
 │
 ├───────────────┐
 │               │
无更新           有更新
 │               │
 │               ▼
 │         git pull --rebase
 │               │
 │          是否冲突？
 │          ┌────┴────┐
 │          │         │
 │         是         否
 │          │         │
 │          ▼         │
 │        解决冲突     │
 │          │         │
 │      rebase continue
 │          │
 └──────────┴─────────┘
            │
            ▼
       git status
            │
            ▼
       检查最终 Commit
            │
            ▼
          git push
            │
            ▼
       验证 Push 成功
            │
            ▼
           完成
```



---

# 44. 简化决策公式

本项目文件推送判断可以概括为：

```text
时间判断
+
Git 状态
+
任务上下文
+
Claude 内容分析
=
最终提交范围
```

而不是：

```text
仅时间判断
```

也不是：

```text
仅 git status
```



---

# 45. Claude 执行原则总结

Claude 在处理 GitHub 推送任务时必须记住：

1. 使用本地 HEAD 的 `Committer Date` 作为时间起点；
2. 使用当前 macOS 系统时间作为时间终点；
3.. 修改文件主要通过 `mtime` 判断；
4.. 新增文件可以通过 Birth Time 辅助判断；
5.. 默认认为 mtime 变化代表真实内容变化；
6.. 时间必须包含日期、时间和时区；
7.. Git 状态负责兜底；
8.. 删除和重命名主要通过 Git 判断；
9.. 最终由 Claude 根据任务上下文决定提交范围；
10.. 不得盲目执行 `git add .`；
11. Commit 前检查 `git diff`；
12.. Push 前必须获取远程仓库最新状态；
13.. 远程有新提交时先同步；
14. 有冲突时先解决冲突；
15. 冲突未解决不得 Push；
16.. 默认禁止 Force Push；
17.. 不得为了同步远程而丢弃本地修改；
18. Push 前必须重新检查最终提交内容；
19.. Push 后确认本地与远程状态；
20.. 下一次任务重新读取新的 HEAD Committer Date.



---

# 46. 最重要的规则

如果时间判断与 Git 状态发生冲突：

```text
时间判断：
这个文件不在时间窗口内

Git：
这个文件仍然存在未提交变化
```

不得直接忽略该文件.



应该：

```text
交给 Claude 检查文件内容
```

然后根据：

```text
当前任务
+
实际 diff
+
文件用途
```

决定是否提交.



因此本项目最终原则是：

> 时间负责定位变化范围，Git 负责验证仓库状态，Claude 负责理解变化内容并做最终决策.



---

# 47. 推送成功标准

只有同时满足以下条件，才认为本次推送任务成功：

```text
本次应提交的文件已经 Commit
+
远程最新代码已经同步
+
不存在未解决冲突
+
Push 成功
+
远程 Branch 已包含本次 Commit
+
不存在因为时间判断而遗漏的合理修改
```

如果仍然存在未提交文件，Claude 必须明确说明：

```text
哪些文件仍未提交
为什么没有提交
是否需要下一步处理
```

不得在存在未知未提交变化时直接宣称：

```text
全部完成
```