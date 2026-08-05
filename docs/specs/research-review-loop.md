# Research Review Lead Loop Specification

## Purpose and boundaries

Research Review Lead Loop（RR Loop）是 Agent Project System 的第一个正式运行模块。它让用户、浏览器端 RR Lead 与本地 IDE Agent 在不能直接互相控制的情况下，通过轻量 Packet、真实执行证据和明确下一步持续推进一个 Work Item。

```mermaid
graph TD
    User([用户]) -- 目标与授权 --> RR[RR Lead]
    RR -- 调研、审查与工作指令 --> IDE[IDE Agent]
    IDE -- Diff、命令与测试证据 --> RR
    RR -- 状态汇报与决策请求 --> User
```

## Roles

- **用户：** 决定目标、优先级、体验、成本、权限、隐私与风险取舍。
- **RR Lead：** 主要用户沟通端；负责必要的外部调研、技术判断、IDE 结果审查和下一目标推进。不得无视本地证据或索取凭据。
- **IDE Agent：** 负责项目内文件编辑、命令执行、测试和本地事实报告。不得隐藏错误、擅自扩大范围、安装未授权依赖或向外发送文件。

RR Lead 监督方向和质量；IDE Agent 用本地事实监督并纠正纸面判断。真实文件、测试输出和 Git Diff 优先于未验证的外部推测。

## Information exchange

- Context Packet：首次同步目标、验收标准与必要背景。
- Change Packet：返回变更摘要、关键 Diff、验证命令、退出码和必要输出。
- Decision Request：仅在用户决策闸口使用。
- Handoff：对话不再可靠继续时的最小接力信息。

模板随源 Skill 包位于 `skills/research-review-lead/assets/`。实际填写的 Packet 默认作为消息传递，不提交到目标项目。浏览器与 IDE 彼此隔离，不依赖自动文件上传。

Evidence Packet 使用通用核心，将目标、范围、产物、验证、来源、不确定性、验收映射、Blocker 和 Debt 分开。Git Diff、命令和退出码只在项目实际使用这些证据时提供；备课、文档、调研和非 Git 项目使用其可复查的产物、来源、覆盖与观察结果。

## Loop

1. IDE 核验当前 Work Item 与本地状态，必要时用 Context Packet 提供背景。
2. RR Lead 检查目标、进行必要调研并下发可执行的 `NEXT_WORK_ORDER` 与验证标准。
3. IDE 在授权范围内执行，用适合当前项目类型的真实证据形成 Evidence Packet。
4. RR Lead 分别给出本轮审查结论和整个任务状态，区分 Blocker 与 Debt，并给出下一步。
5. 达到验收标准时任务进入 `ACHIEVED`；需要用户决定时进入 `NEEDS_DECISION`；否则继续推进。

## Review decision and work item state

两个字段不得混用：

```text
REVIEW_DECISION:
PASS / PASS_WITH_DEBT / REVISE / ESCALATE

WORK_ITEM_STATE:
IN_PROGRESS / ACHIEVED / BLOCKED / NEEDS_DECISION / STALLED / UNSAFE
```

例如 `REVIEW_DECISION: PASS_WITH_DEBT` 与 `WORK_ITEM_STATE: IN_PROGRESS` 表示本轮实现通过但整个任务仍需继续。

RR Lead 每轮响应还应包含 `GOAL_CHECK`、`FINDINGS`、`BLOCKERS`、`DEBT`、`NEXT_WORK_ORDER`、`VALIDATION` 和 `USER_DECISION_REQUIRED`。非阻塞建议只能进入 Debt，不能阻止主线完成。

## Sixth-round health checkpoint

第六轮是强制健康检查点，不是硬性终止上限。检查：

- 是否忘记原目标；
- 是否发生范围漂移；
- 是否重复相同建议；
- 是否没有新增证据；
- 是否已经陷入停滞；
- 当前对话是否仍能可靠继续。

没有异常时允许继续同一 Work Item。只有出现上述问题、硬阻塞、长时间等待决定或对话已不可靠时，才生成 Handoff 并考虑切换对话；不得为了轮数机械结束任务，也不猜测 Token 上限。

## Handoff and resume

- 源 Skill 包只保留一个 `assets/handoff.md` 权威模板，不为 IDE Agent 和 RR Lead 创建两套独立模板。
- 所有交接都填写 Common Handoff Core：Work Item ID、Conversation ID、交接原因、目标、验收标准、任务状态、确认事实、已有决定、Blocker、Debt、下一步和必读权威文件。
- IDE Agent 交接时再填写 IDE Agent Extension，提供仓库、Git、命令、退出码、测试、关键 Diff、本地限制和禁止重复的失败路径。
- RR Lead 交接时再填写 RR Lead Extension，提供用户意图、待决策项、外部调研、已否定路线、审查结论、任务状态、判断理由、下一工作指令和漂移检查。
- 未交接的角色扩展直接省略，不填写大量“不适用”字段，也不复制模板。
- 不得为了 Handoff 默认执行 `git add` 或 `git stash`，不得擅自改变用户工作区。
- 实际 Handoff 默认只作为消息；长期事实更新到唯一的 `docs/current.md`。
- 不在 `state/` 或其他目录积存日期 Handoff。只有用户明确批准后，实际 Handoff 才可通过文档闸门长期保存。
- 接手者先读 `docs/current.md` 与相关证据，从明确的下一动作继续。

## User decision gates

只在以下情况暂停：目标或产品方向变化；成本或付费；账号和权限；隐私和私人数据；文件公开或上传；删除、覆盖或其他不可逆操作；重大安全风险；当前目标无法实现且需要接受降级。决策请求必须给出三个白话选项和一个推荐。

## MVP limits

第一版只允许一个 Active Work Item；不开发多任务调度、自动通知、GitHub Issues/Projects 同步或图形界面。普通 Git 与远端仓库可用于保存历史。

RR Lead 在具有项目权威入口时采用 Full Governance Mode，并服从目标项目自己的规则和状态源；没有完整治理结构时采用 Compatibility Mode，以用户请求和现有入口运行，不强制 Git、`docs/current.md` 或治理初始化。
