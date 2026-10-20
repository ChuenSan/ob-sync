# AGENTS.md

本文件为 AI 编程助手（如 Codex、Agent）识别本项目上下文时的入口文件。



##  #####必读

> 工作前必读：请直接读取本仓库根目录下的 [CLAUDE.md](CLAUDE.md) 文档。它规定了本项目全部协作与 Git 同步规则，是本项目的权威项目记忆与操作手册.



CLAUDE.md 中明确了：

- 本项目 GitHub 文件同步、提交与推送的完整逻辑；
- 时间窗口限定本次范围、Git 状态验证实际差异的判断流程；
- Commit、Rebase、Push、冲突处理等操作的执行规范；
- 禁止的高风险操作与敏感文件检查要求.



所有与本项目（尤其 Git 同步、文件变更、推送）相关的任务，请以 CLAUDE.md 为准执行.

涉及待提交文件检查、确定提交范围或提交/同步时，必须按 `CLAUDE.md` 第 1.4 节，先运行 [scripts/pending_commit_audit.py](scripts/pending_commit_audit.py)，读取本次最新完整结果，再审查候选内容。不能用脚本源码或旧输出代替检查，也不能把候选列表直接当作提交授权；具体分类、阻断条件及完整流程统一以 `CLAUDE.md` 为准。

若本文件与 CLAUDE.md 冲突，以 CLAUDE.md 为准。