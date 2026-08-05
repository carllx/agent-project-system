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

## Goal Contract and information exchange

Context Packet 必须定义所有参与者共同使用且不会被 RR Lead 静默扩大的 Goal Contract：`WORK_ITEM_ID`、`SHARED_OBJECTIVE`、`ACCEPTANCE_CRITERIA`、`SCOPE`、`CONSTRAINTS`、`EVIDENCE_REQUIRED` 和 `STOP_CONDITIONS`。新发现但不阻塞本目标的改进进入 Debt；改变验收条件必须由用户明确决定。

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

只要 Work Item 为 `IN_PROGRESS`、存在可执行的 `NEXT_WORK_ORDER`、没有用户决定或安全风险，并且存在新增证据或合理新路径，循环就继续。协议不使用“无限循环”：`ACHIEVED`、`BLOCKED`、`NEEDS_DECISION`、`STALLED` 和 `UNSAFE` 都会停止本地执行。

## Review decision and work item state

两个字段不得混用：

```text
REVIEW_DECISION:
PASS / PASS_WITH_DEBT / REVISE / ESCALATE

WORK_ITEM_STATE:
IN_PROGRESS / ACHIEVED / BLOCKED / NEEDS_DECISION / STALLED / UNSAFE
```

例如 `REVIEW_DECISION: PASS_WITH_DEBT` 与 `WORK_ITEM_STATE: IN_PROGRESS` 表示本轮实现通过但整个任务仍需继续。

RR Lead 每轮响应还应包含 `ACCEPTANCE_STATUS`，逐条给出 Criterion、`MET / NOT_MET / UNVERIFIED`、Evidence，并包含 `FINDINGS`、`BLOCKERS`、`DEBT`、`NEXT_WORK_ORDER`、`VALIDATION` 和 `USER_DECISION_REQUIRED`。非阻塞建议只能进入 Debt，不能阻止主线完成；只有所有原验收条件都有充分证据且为 `MET` 才能进入 `ACHIEVED`。

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

## OpenCLI runtime orchestration

运行循环明确区分三类 Agent：Builder IDE Agent 只维护源包；IDE-side Loop Driver 在目标项目读取事实、交换 Packet 并执行 Work Order；Browser RR Lead 必须真实存在于 ChatGPT 浏览器对话中，负责外部调研、审查和推进。Loop Driver 不得冒充 Browser RR Lead，也不得用本地意见伪造浏览器回复。

目标循环为：

```text
共同目标
→ IDE 执行
→ IDE 提交证据
→ RR Lead 按验收标准审查
→ 未达到则给修复指令
→ IDE 修复并重新提交证据
→ 全部达到则 ACHIEVED
```

Loop Driver 必须保存 Work Item ID、Conversation ID 或 URL、轮次、最后成功读写时间和当前状态，不得只依赖当前浏览器标签页。只有状态为 `IN_PROGRESS`、不存在用户决策闸口且操作在授权范围内时才执行 `NEXT_WORK_ORDER`。

当 Browser RR Lead 返回 `NEEDS_DECISION` 时，Loop Driver 停止执行并等待用户在同一 Browser 对话中回答。用户明确表示已回答后，Loop Driver 用记录的对话身份重新读取，核对 Work Item 和选择，形成 Decision Receipt，再恢复原循环；第一版不自动轮询。

### Transport Smoke 取证事实

2026-08-05 的 `TRANSPORT-SMOKE-001` 产生了两次 `ask --new` 超时。只读 history/detail 恢复确认两个命令分别建立了一个对话，两个用户消息均已投递，两个 Browser 回复均已完成；同一 Work Item 因超时后重发而出现一个额外重复对话。显式 Conversation ID detail 对两个对话均可稳定恢复。OpenCLI 输出不含消息时间戳，因此本次无法从 CLI 精确证明消息和回复时刻。

故障发生在创建和投递之后的等待完成检测或结果返回边界，而不是已证实的发送失败。history 的观测顺序不能当作 newest-first 合约；恢复必须比较发送前后的 ID 集合，再以唯一 `MESSAGE_ID` 核验候选对话。

`TRANSPORT-RECOVERY-002` 又证明 `ask --new` 可能在两个发送前已存在的 Conversation 之间错投：命令报告目标 Conversation 与最终页面 URL 不同，Runtime 只记录 `DELIVERY_UNKNOWN`，而旧恢复逻辑排除了所有发送前 ID，导致已送达消息不可恢复。该实验随后发生计划外发送和探针污染，因此不得作为 A2 通过证据。

### Delivery state and identity

每个 Browser 消息必须包含 `WORK_ITEM_ID`、唯一 `MESSAGE_ID`、`ROUND` 和 `MESSAGE_TYPE`。同一个 `MESSAGE_ID` 在确认失败前不得重发。传输维护：

```text
NOT_SENT
CREATING_CONVERSATION
VERIFYING_CONVERSATION
SENDING
SENT
DELIVERY_UNKNOWN
MISROUTED_DELIVERY
DELIVERED
RESPONSE_PENDING
RESPONSE_READY
FAILED
```

CLI timeout 首先进入 `DELIVERY_UNKNOWN`。`MISROUTED_DELIVERY` 表示消息已确认送达，但进入发送前已存在且不是当前 Work Item 目标的 Conversation。进入后必须禁止相同 Message ID 重发、禁止继续使用错误 Conversation、禁止把其回复作为正式 RR Lead 输出，只记录错误 Conversation ID 与精确 Work Item/Message ID 命中的最少证据，并返回 Work Item `BLOCKED` 请求修复创建流程。旧 Conversation 命中永远不得晋升为 `DELIVERED`。

传输拆成：

```text
PREPARE_MESSAGE
→ CREATE_NEW_CONVERSATION
→ VERIFY_NEW_CONVERSATION
→ SEND_MESSAGE
→ CAPTURE_OR_RECOVER_CONVERSATION_ID
→ POLL_OR_READ_RESPONSE
→ PARSE_RR_REVIEW
```

新 Conversation 发送前先记录活动 URL 和有限最近 ID，单独执行 `opencli chatgpt new`，再用 `status` 证明 URL 已变化且不在任何旧 `/c/<id>` 页面，并用 `read` 证明当前页面为空。只有这些条件全部满足才在当前已验证空白页执行一次 `ask`，不得再用 `ask --new` 承载真实 Work Item。OpenCLI 自动验证失败时，降级为用户人工打开空白 ChatGPT 根 URL 并提供 URL；Wrapper 仍必须核对当前 URL 完全一致且页面为空，不允许口头确认绕过验证。

正常恢复不得扫描全部 pre-send Conversation。只允许优先检查发送后当前活动 Conversation，再检查配置限定的少量最近候选；只搜索精确 `WORK_ITEM_ID` 与 `MESSAGE_ID`，命中立即停止，不保存无关正文。

Runtime State 至少记录 `work_item_id`、`message_id`、`expected_conversation_mode`、`pre_send_active_conversation_id`、`verified_target_conversation_id`、`actual_delivery_conversation_id`、`delivery_state`、`send_attempt_count`、`recovery_attempt_count`、`misroute_detected`、`started_at`、`stopped_at` 和 `stop_reason`。记录位于系统临时目录且不保存 Cookie、Token 或账号凭据；完成后显式清理。

默认实验预算为 `MAX_SEND_ATTEMPTS_PER_MESSAGE=1`、`MAX_RECOVERY_ATTEMPTS=1`、`MAX_DETAIL_CHECKS=1`、`MAX_EXTERNAL_COMMANDS=8`、`MAX_EXPERIMENT_SECONDS=60`。数值可以在受控实验配置中进一步收紧或明确调整，但必须有限；任一上限到达立即停止。

### A2.1 preparation interface

Wrapper 必须提供独立公开命令 `prepare-new --runtime-dir <path> --work-item-id <id>`。它只执行：

```text
CREATE_NEW_CONVERSATION
→ VERIFY_NEW_CONVERSATION
→ PERSIST_RUNTIME_STATE
→ STOP_WITHOUT_SEND
```

`prepare-new` 是 A2.1，只创建并验证空白新对话；`send` 是 A2.2/A3，才负责发送消息。A2.1 必须记录操作前 URL 与旧 Conversation ID，执行一次 `new`，证明最终 URL 已离开旧 `/c/<id>` 且为 ChatGPT 根页面或 `/new`，再执行一次只读 `read`。本命令将 `EMPTY_RESULT` 解释为空页面验证成功，但不得调用 `ask` 或 `send`、不得创建 Message ID，且 `PREPARED_NEW_CONVERSATION` 不代表消息已投递或 A2.2 已通过。

A2.1 在 Wrapper 内固定强制 `MAX_SEND_ATTEMPTS=0`、`MAX_RECOVERY_ATTEMPTS=0`、`MAX_DETAIL_CHECKS=0`、`MAX_EXTERNAL_COMMANDS=4`、`MAX_EXPERIMENT_SECONDS=60`。六十秒覆盖 Wrapper 启动及全部子命令和轮询；预算耗尽时停止后续命令并持久化 `stop_reason=BUDGET_EXHAUSTED`。Runtime 至少保存 `work_item_id`、`operation=PREPARE_NEW`、`pre_operation_url`、`pre_operation_conversation_id`、`post_operation_url`、`verification_result`、`read_result`、`message_send_count=0`、`external_command_count`、`started_at`、`stopped_at`、`elapsed_seconds`、`stop_reason` 和 `test_result`。允许结果仅为 `PREPARED_NEW_CONVERSATION`、`BLOCKED_BEFORE_SEND`、`BUDGET_EXHAUSTED`、`TEST_PROTOCOL_VIOLATION`。

本机 OpenCLI `1.8.6` help 已确认 `new` 只声明输出 `Status`，`status` 声明输出当前 URL，`read` 可检查当前页面消息；因此独立创建后必须组合 URL 与空页面验证。`send` 的创建、目标绑定、身份返回和实际投递行为仍为 `UNVERIFIED`，正式脚本不依赖它。

### 实验 Agent 协议

每条 Transport 或 Loop 实验 Prompt 都必须明确禁止实验 Agent：修改 Skill、修改 Wrapper、重置 Runtime 后重试、重发相同 Message ID、发送计划外 hello/test 探针、阅读无关 Browser 对话、自行修复代码、把测试转化成开放式研发任务。任一违反立即记为 `HARD_FAILURE: TEST_PROTOCOL_VIOLATION`，停止并废弃该轮通过结论。

## Validation layers

四层验证不得混用：

1. **静态测试：** Skill 发现、五份 Asset 读取、模式识别、格式和包检查。
2. **传输测试：** OpenCLI 状态、新建 Browser 对话、发送和读取、Conversation ID 捕获、显式 ID 同对话续聊。
3. **循环测试：** Context Packet、Browser Work Order、IDE 执行、Evidence Packet、第二轮 Browser 审查和正确停止。
4. **Human-in-the-loop 测试：** `NEEDS_DECISION`、IDE 停止、用户在 Browser 回答、同对话读取、Decision Receipt 和原循环恢复。

静态测试通过只证明包结构和规则存在，不能证明传输、循环或人工决策恢复有效。

### Experiment A1: Non-mutating recovery regression

使用已知 Conversation ID 和已知 `MESSAGE_ID` 验证 wrapper 的 recover 分支可返回 `RESPONSE_READY`，且不发送消息。

### Experiment A2.1: Prepare new without send

使用新的 Work Item ID 和 Runtime 目录调用公开 `prepare-new`，只验证新空白对话与正式 Runtime 状态。该实验不得发送消息，成功结果只为 `PREPARED_NEW_CONVERSATION`。

### Experiment A2.2: One-send transport

在 A2.1 独立通过后，使用新的无副作用 Work Item、单一 `MESSAGE_ID` 和全新 Runtime 目录验证 `SEND_MESSAGE`、身份捕获或一次恢复及无重复投递。执行前需用户授权真实 Browser 写入；`TRANSPORT-RECOVERY-002` 不得用于判定通过。

### Experiment A3: `send` candidate

在隔离对话中验证 `send` 是否要求先创建或打开对话、如何绑定明确 Conversation ID、是否只发送不等待，以及如何证明发往正确对话。通过前保持 `UNVERIFIED`。

### Experiment B: Two-round Loop

只有 A2 与 A3 都通过后才开始正式 Loop。核验 OpenCLI 和 Browser Bridge 状态；创建真实 Browser RR Lead 对话；发送初始化规则与 Context Packet；取得固定格式回复；捕获 Conversation ID/URL；使用显式身份重新读取并发送一条无副作用验证消息；确认响应属于同一目标对话。

使用备课 fixture，至少执行两个完整的 `IDE 执行 → Evidence Packet → RR Lead 审查` 循环。验收标准未全部 `MET` 时不得返回 `ACHIEVED`。

### Experiment C: Human Decision Resume

使用安全决策 fixture：Browser RR Lead 返回 `NEEDS_DECISION`；IDE 停止；用户在 Browser 选择；IDE 在用户确认后重新读取同一对话；核对决定并生成 Decision Receipt；只恢复被选择的路径。

写入型实验是下一阶段；本次源包修改只执行只读恢复取证和本地静态验证。
