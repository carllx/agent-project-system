# Handoff Template

> 本文件是唯一的可复用 Handoff 模板，不是某一次实际运行记录。填写后的临时 Handoff 默认不得提交到仓库。

所有交接都填写 Common Handoff Core，再根据交接方选择一个角色扩展。不要复制本文件创建第二套 IDE 或 RR Lead Handoff 模板。

## Common Handoff Core

- **Work Item ID:** [当前工作项标识]
- **Conversation ID:** [交出方当前对话标识]
- **Handoff reason:** [为什么当前对话无法可靠继续]
- **Current goal:** [用户确认的当前目标]
- **Acceptance criteria:** [仍适用的完成标准]
- **Work Item state:** [IN_PROGRESS / ACHIEVED / BLOCKED / NEEDS_DECISION / STALLED / UNSAFE]

### Confirmed facts

- [由文件、命令、测试、用户决定或可靠来源支持的事实]

### Decisions already made

- [已经确认且不得重新讨论的决定]

### Blockers

- [影响当前验收标准的问题或 None]

### Debt

- [不阻塞当前目标的发现或 None]

### Next action

- [接手者可以立即执行的一项具体动作]

### Authority files to read

- [接手者必须读取的最小权威文件集合]

## IDE Agent Extension

IDE Agent 交接时填写本节；RR Lead 交接时省略本节。

- **Repository root:** [项目根目录]
- **Branch:** [当前分支]
- **Baseline commit:** [基线 Commit]
- **Git status:** [真实 `git status --short --branch` 摘要]
- **Modified files:** [本 Work Item 已修改的文件]
- **Commands run:** [已运行命令]
- **Exit codes:** [对应退出码]
- **Test results:** [测试或检查结果]
- **Key diff:** [必要的关键 Diff 或其路径]
- **Local environment constraints:** [本地限制]
- **Failed paths not to repeat:** [已验证失败且无新证据时不得重试的路径]

## RR Lead Extension

RR Lead 交接时填写本节；IDE Agent 交接时省略本节。

- **Confirmed user goals and preferences:** [用户已确认内容]
- **Pending user decisions:** [用户尚未决定的问题或 None]
- **External research and sources:** [必要结论与来源]
- **Rejected technical paths:** [已经否定的路线及理由]
- **Review decision:** [PASS / PASS_WITH_DEBT / REVISE / ESCALATE]
- **Work Item state:** [当前任务状态]
- **Current rationale:** [当前判断理由]
- **Next work order:** [下一条明确的 `NEXT_WORK_ORDER`]
- **Drift or repetition check:** [是否出现目标漂移或重复]
- **Resume point:** [下一任 RR Lead 从哪里继续]

## Handling rules

- 生成 Handoff 不得默认执行 `git add` 或 `git stash`，不得擅自改变用户工作区。
- 实际 Handoff 默认只作为消息传递，不创建日期、`final`、`v2` 或角色副本文件。
- 需要长期保留的事实更新到 `docs/current.md`，规则或设计决定更新到适用的 Spec 或 ADR。
- 长期保存某次实际 Handoff 必须先获得用户明确批准并通过文档创建闸门。
