# OpenCLI Session Discovery and Identity Contract

## Authority and scope

本 Spec 是 Agent Project System 对 OpenCLI / Browser Session Discovery 与 Conversation identity 的产品权威。它定义 `CREATE → CAPTURE → VERIFY → SEND → VERIFY DELIVERY → RECOVER` 的身份与状态语义，为 `OPENCLI-SESSION-DISCOVERY-001` 的实现和 Lab 验证提供边界。

本 Contract 属于 Transport Adapter 层，不改变 ACF Review Protocol、Completion Authority 或 IDE Adapter。Agent Project System 拥有 Problem、Contract、Acceptance Criteria、状态语义与 Product implementation；`rr-lead-skill-lab` 只验证 OpenCLI / Browser 的未知机制并返回 Evidence 与 Reference Implementation。

## Problem statement

此前真实运行不能稳定区分“创建了页面”“准备发送的目标”“Browser 当前打开位置”“消息实际送达位置”和“timeout 后恢复出的候选”。把这些值统称为 Conversation ID 会让错误页面、错投或无身份 timeout 被误判为成功，并诱发重复发送。

本 Contract 强制区分：

- `CREATED_CONVERSATION_ID`: 创建操作直接返回或由创建结果直接证明的新 Conversation identity。`/new`、根页面或空页 Evidence 不是 Conversation ID；没有直接证据时为 `UNAVAILABLE`。
- `TARGET_CONVERSATION_ID`: 单次发送在写入前绑定的预期唯一目标。它来自已验证的 existing Conversation 或经验证的 create/capture 结果；不得由 Browser 当前标签、history 顺序或回复正文推断。
- `CURRENT_BROWSER_CONVERSATION_ID`: 某次 `status` 观察时，Browser 精确 `https://chatgpt.com/c/<id>` URL 中的 identity。根页面、`/new`、其他 host 或非精确路径产生 `NONE`。它只说明当时页面位置，不证明发送目标或投递结果。
- `DELIVERY_CONVERSATION_ID`: exact-ID read/detail 或与发送结果不可拆分的返回值证明同时包含当前 `WORK_ITEM_ID` 与 `MESSAGE_ID` 的 Conversation identity。它是实际投递身份，不由 status 单独建立。
- `RECOVERED_CONVERSATION_ID`: timeout 或身份缺失后，在有限恢复中选出的唯一、精确核验候选。它必须记录来源；只有 exact marker Evidence 通过后才能同时成为 `DELIVERY_CONVERSATION_ID`。

五个字段不得互相覆盖。相同字符串可以在验证后出现在多个字段中，但每个字段必须保留自己的来源与建立时点。

## Evidence classes

身份 Evidence 只采用以下最小分类：

- `AUTHORITATIVE_IDENTITY_EVIDENCE`: OpenCLI 结构化结果中的 identity 与同一结果中的 exact URL 一致；或针对显式 ID 的 exact detail/read 返回该 Conversation 的消息。
- `CURRENT_PAGE_EVIDENCE`: `status` 返回精确 ChatGPT `/c/<id>` URL，只能建立 `CURRENT_BROWSER_CONVERSATION_ID`。
- `DELIVERY_MARKER_EVIDENCE`: 同一个 Conversation 的 user-role message 精确包含当前 `WORK_ITEM_ID` 与唯一 `MESSAGE_ID`。
- `CANDIDATE_ONLY`: history 差集、标题、顺序、页面导航、根页面、`/new` 或单独的 status 观察。它们可以缩小恢复范围，不能单独证明 target 或 delivery。

任何来源冲突、重复候选、identity/URL 不一致、不可解析结构或缺失 marker 都不得“择一相信”，而应保持未验证状态。

## Product flow

### 1. CREATE

创建动作必须与发送分离记录。它可以产生空白 Browser 环境，也可以产生 `CREATED_CONVERSATION_ID`；只有真实输出直接给出稳定 ID 或精确 `/c/<id>` 并能由相同创建结果绑定时，后者才成立。

已知 OpenCLI 1.8.6 `new` 只声明 `Status`，当前历史只证明它可把 Browser 带到根页面或 `/new`。因此 Product 当前不得把 `new` 成功、页面为空或 `EMPTY_RESULT` 写成 `CREATED_CONVERSATION_ID`。

### 2. CAPTURE

Capture 收集每个 identity observation 与来源，不立即把候选提升为 target 或 delivery。至少记录：

```text
IDENTITY_VALUE
IDENTITY_ROLE
SOURCE_KIND
OBSERVED_AT
WORK_ITEM_ID
MESSAGE_ID: when applicable
```

相同角色出现不同非空值时进入 `IDENTITY_CONFLICT`；不得覆盖先前值。history 只允许使用发送前保存的有限基线与一次相同窗口 refresh，不能依赖 newest-first 排序，也不能扫描全部对话。

### 3. VERIFY

发送前必须建立一个明确的 `TARGET_CONVERSATION_ID`。Existing 模式要求显式目标 ID，并通过受限 status/history/detail Evidence 证明该 identity 存在且与当前发送机制可绑定。New 模式只有在创建/捕获机制产生可验证 exact ID 时才能在发送前绑定；如果 OpenCLI 只能在第一条消息写入后才生成 ID，则该能力缺口必须由 Lab 明确，Product 不得伪造 pre-send target。

`CURRENT_BROWSER_CONVERSATION_ID == TARGET_CONVERSATION_ID` 只在发送机制依赖当前页面时是必要条件；若未来命令有被真实验证的 explicit target 参数，则 Browser 可以打开其他页面，但命令返回与投递仍必须证明目标一致。当前是否存在这种可靠机制为 `UNVERIFIED`。

### 4. SEND

发送前持久化 `WORK_ITEM_ID`、`MESSAGE_ID`、`TARGET_CONVERSATION_ID`、目标 Evidence、`send_attempt_count=0` 与状态。实际写命令调用边界必须先原子记录 `send_attempt_count=1`。

同一 `MESSAGE_ID` 最多一次写入尝试。timeout、进程崩溃、无 ID、identity conflict、`DELIVERY_UNKNOWN`、`MISROUTED_DELIVERY` 或恢复失败都不授权 resend。只有创建新的 Message ID 并获得协议或用户授权时才可能发起新的逻辑消息；不得用新 ID 隐藏旧消息投递不明。

### 5. VERIFY DELIVERY

发送成功返回码、Browser status、history 新增行或页面跳转都不足以单独证明 delivery。只有下列条件全部满足才建立 `DELIVERY_CONVERSATION_ID`：

1. Evidence 与一个精确 Conversation ID 绑定；
2. 该 Conversation 的 user-role message 精确包含当前 `WORK_ITEM_ID` 与 `MESSAGE_ID`；
3. marker 命中唯一；
4. identity 来源之间没有未解决冲突。

若 `DELIVERY_CONVERSATION_ID == TARGET_CONVERSATION_ID`，进入 `DELIVERED` 或后续 response 状态。若 marker 在发送前已存在且非目标的 Conversation 中命中，进入 `MISROUTED_DELIVERY`。若证据不足或多个候选都可能成立，进入 `DELIVERY_UNKNOWN`。

### 6. RECOVER

Recovery 只在一次发送尝试之后进行，不写消息。允许的顺序是：

```text
PERSISTED_TARGET_OR_ASK_IDENTITY
→ POST_SEND_CURRENT_BROWSER_ID
→ ONE BOUNDED HISTORY DIFF
→ ONE EXACT-ID DETAIL CHECK
```

只有已有 `TARGET_CONVERSATION_ID`，或 bounded evidence 得到唯一候选时，才允许 exact-ID recovery。选中候选时记录 `RECOVERED_CONVERSATION_ID` 与来源；detail 中 exact Work Item/Message marker 成功后才能建立 delivery。无候选、多候选、来源冲突、detail 不可读或 marker 不唯一时必须保持 `DELIVERY_UNKNOWN`，停止自动执行并禁止 resend。

## Mismatch detection

每次发送前后都独立记录 `CURRENT_BROWSER_CONVERSATION_ID`。以下情况必须显式暴露：

- 依赖当前页面的发送中，发送前 current 与 target 不同：发送前阻止。
- ask/report identity 与发送后 current 不同：`IDENTITY_CONFLICT`，进入 bounded recovery，不把任一方直接认作 delivery。
- delivery 与 target 不同：`MISROUTED_DELIVERY`；错误 Conversation 的回复不具备正式 Browser Review 资格。
- current 与 delivery 不同但 explicit target mechanism 已被真实验证：记录 navigation mismatch，不自动判错投；delivery 仍由 marker Evidence 决定。

## State semantics

本 Contract 复用现有 delivery 状态，不增加无必要的并行状态机：

```text
NOT_SENT
→ CREATING_CONVERSATION
→ CAPTURING_IDENTITY
→ VERIFYING_CONVERSATION
→ SENDING
→ SENT / DELIVERY_UNKNOWN / MISROUTED_DELIVERY
→ DELIVERED
→ RESPONSE_PENDING / RESPONSE_READY
```

`IDENTITY_CONFLICT` 是阻止状态迁移的事实，不是投递成功状态。`DELIVERY_UNKNOWN` 表示无法证明成功或失败；它永远不等于 `FAILED`，也不允许 resend。`RECOVERED_CONVERSATION_ID` 只是 recovery 结果字段，不是 delivery state。

## Known facts from project evidence

- `/new` 和 ChatGPT 根页面不是精确 Conversation；空页 `EMPTY_RESULT` 只证明没有可读消息。
- OpenCLI 1.8.6 `new` 只观察到 `Status`；`status` 可返回当前 URL；`history` 返回 ID/URL 但顺序不是可靠 newest-first contract；显式 ID `detail` 可读取已观察到的 timed-out Conversation。
- `ask --new` 曾 timeout 后实际创建并投递到两个不同 Conversation，也曾把消息送入发送前已存在的非目标 Conversation；因此已从正式路径禁止。
- `send --prepare-new` 已实现 pre-send bounded history、`new`、URL/empty-read verification、单次 `ask`、ask JSON/flat-YAML identity parsing、post-send status 与必要的一次 history/detail recovery。
- 结构化 stderr `EMPTY_RESULT` 是已知的非零退出空页例外；未知或不可解析 read 输出必须阻止发送。
- timeout 进入 `DELIVERY_UNKNOWN`；同一 Message ID 不得重发。exact marker 在发送前非目标 Conversation 命中时为 `MISROUTED_DELIVERY`。
- 当前实现已有 `pre_send_active_conversation_id`、`verified_target_conversation_id`、`ask_reported_conversation_id`、`post_send_active_conversation_id`、`actual_delivery_conversation_id` 与 `candidate_conversation_id`，但这些 legacy fields 尚未完整映射本 Contract 的五类 identity。

## Unknown mechanisms requiring Lab evidence

- `opencli chatgpt new` 后是否存在任何不发送消息即可取得稳定 exact Conversation ID 的机制。
- OpenCLI 是否有可验证的 explicit-target 写命令，可在 Browser 当前页面不同的情况下仍把消息只送到指定 Conversation，并返回同一 identity。
- 新 Conversation 第一条写入若负责生成 ID，什么最小原子 Evidence 可以同时证明 target intent、returned identity 与 actual delivery，而不把 post-send observation 伪写成 pre-send binding。
- ask/report identity、Browser status URL 与 exact detail 在 timeout 或 navigation error 时的稳定关系。

这些问题不能从当前代码或历史文档继续推断，必须由一个有界 Lab 实验回答；不得通过 Product Agent 无休止操作 Browser 来填补。

## Product implementation requirements

实现必须以本 Contract 的五类 identity 为显式字段，保留 observation provenance，并对 legacy state 做明确迁移或拒绝，不得静默改义。Session discovery 与 delivery verification 必须可单元测试，OpenCLI 命令执行只是 Adapter；核心判断不得依赖 Browser 标题、history 排序或活动标签假设。

任何 Lab Probe 只作为 Reference Implementation + Evidence。Product implementation 必须重新纳入项目 Contract、预算、状态持久化、marker 验证与隐私边界，删除 Lab workspace、experiment、conversation 与临时路径硬编码。

## Acceptance Criteria

1. 五类 Conversation identity 在 Product Contract 与 Runtime State 中显式区分，来源和建立时点可审查。
2. `CREATE → CAPTURE → VERIFY → SEND → VERIFY DELIVERY → RECOVER` 每一步的输入、成功证据与失败语义明确。
3. 新建 Conversation 后取得 exact ID 的机制由现有 Evidence 或最小 Lab 实验证明；不能证明时 Product 阻止需要 pre-send target 的正式发送，不伪造身份。
4. 发送前 `TARGET_CONVERSATION_ID` 绑定规则明确，Browser 当前页面与 target 不一致可被检测。
5. `DELIVERY_CONVERSATION_ID` 只能由 identity-bound exact Work Item/Message marker Evidence 建立，status/history 顺序不能单独通过。
6. timeout、identity conflict、misroute、exact-ID recovery 与 `DELIVERY_UNKNOWN` 的状态迁移明确且有界。
7. 每个 Message ID 最多一次写入尝试；`DELIVERY_UNKNOWN`、`MISROUTED_DELIVERY` 和恢复失败绝对禁止 resend。
8. Product implementation 与 regression tests 覆盖正确绑定、错页、缺失 ID、冲突 ID、唯一恢复、多候选、marker 缺失/重复和 no-resend。
9. Contract 与实现不把 OpenCLI、GitHub 或 Browser 当前标签提升为 ACF Completion Authority，也不改变 ACF-0.1。
10. Lab 只验证真正未知的 Session mechanism；普通 send/receive、Stop Hook、Completion Gate 与已证实 EMPTY_RESULT 不重复实验，文档不存在重复 SSOT。

## Minimal Lab experiment handoff

```text
LAB_EXPERIMENT_HANDOFF
WORK_ITEM_ID: OPENCLI-SESSION-DISCOVERY-001
EXPERIMENT_ID: OPENCLI-SESSION-IDENTITY-MIN-001
OWNER: rr-lead-skill-lab
PRODUCT_BASELINE_SHA: d73314ad44e72ea78b8729b593a1b797362c46af
PURPOSE: Determine the smallest reliable OpenCLI mechanism that yields and binds an exact Conversation identity for a newly created Browser session, and distinguish it from current-page and delivery identities.

PRECONDITIONS:
- Use the Lab repository and a fresh experiment Runtime.
- Use the currently installed OpenCLI version and record the exact version.
- Browser Bridge connected and ChatGPT logged in; do not inspect credentials.
- Fresh WORK_ITEM_ID and one unique MESSAGE_ID containing an inert marker payload.

QUESTIONS:
1. After one `opencli chatgpt new`, can any read-only command return a stable exact `/c/<id>` before a message is sent? Record `new`, `status`, `read`, and only the bounded history delta needed to answer.
2. If no pre-send ID exists, which single supported write path returns an exact identity for the first message, and can the same run prove that exact marker is in that identity?
3. For an explicit existing target, does the supported explicit-target write path deliver only to that ID when Browser status is on a different Conversation, and do returned identity, post-send status, and exact detail agree or conflict?
4. On timeout/navigation error, which exact-ID evidence remains available without a second send?

RULE_A_EXPLICIT_TARGET_MECHANISM:
- Before an explicit-existing-target write, perform only the read-only static checks needed against CLI help, the installed OpenCLI command definition/source, and existing project Evidence.
- Execute the second write only when an actually supported explicit-target write mechanism exists.
- If none exists, report `EXPLICIT_TARGET_WRITE_MECHANISM: NOT_AVAILABLE` and `QUESTION_3: UNVERIFIED / NOT_AVAILABLE`.
- Do not guess a flag, invent an API, modify OpenCLI, or implement a temporary target-write mechanism for the experiment.

RULE_B_NO_MANUFACTURED_TIMEOUT:
- Question 4 observes only timeout/navigation error that occurs naturally during an otherwise authorized write.
- If both legal writes complete normally, report `TIMEOUT_RECOVERY_OBSERVATION: NOT_OBSERVED` and `QUESTION_4: UNVERIFIED`.
- Do not add writes, polls, sleeps, network interference, or Browser manipulation to manufacture a timeout.

RULE_C_EVIDENCE_FIRST:
- Before every action record `ACTION_ID`, `COMMAND`, `INTENDED_IDENTITY_ROLE`, `PRE_STATUS_URL`, and `PRE_BOUNDED_ID_SET`.
- After the action record `EXIT_CODE`, `STDOUT_STDERR_CLASSIFICATION`, `RETURNED_IDENTITY`, `POST_STATUS_URL`, `POST_BOUNDED_ID_SET`, and `EXACT_MARKER_RESULT`.
- Perform identity classification only after those observations are recorded; never infer a Conversation ID first and backfill Evidence.

ACTION_BUDGET:
- At most two write attempts total: one new-session marker and one explicit-existing-target marker.
- Each write uses a different MESSAGE_ID and is attempted once.
- At most one `new`; one pre-send status/read sequence; one bounded pre/post history window per write; one post-send status and one exact detail per candidate.
- No resend, no broad history scan, no unrelated Conversation reads, no ordinary ACK/smoke loop, no code repair, no Hook/Completion-Gate experiment.
- MAX_IDLE_WAIT_SECONDS=0; MAX_SCHEDULE_CALLS=0; MAX_POLL_ATTEMPTS=0.

REQUIRED_EVIDENCE:
- Raw command, exit code, stdout/stderr classification and timestamps for each authorized action.
- CREATED_CONVERSATION_ID, TARGET_CONVERSATION_ID, CURRENT_BROWSER_CONVERSATION_ID, DELIVERY_CONVERSATION_ID and RECOVERED_CONVERSATION_ID reported separately; use UNAVAILABLE/NONE when not proven.
- Exact Work Item/Message marker evidence only; redact unrelated message bodies.
- Pre/post Browser status URLs and bounded pre/post Conversation ID sets.
- A truth table showing which source can authoritatively establish each identity role.
- `EXPLICIT_TARGET_WRITE_MECHANISM` and `TIMEOUT_RECOVERY_OBSERVATION`, including the required `NOT_AVAILABLE` / `NOT_OBSERVED` outcomes when applicable.

STOP_CONDITIONS:
- Any write timeout becomes DELIVERY_UNKNOWN until exact-ID recovery completes; never resend.
- More than one candidate, identity conflict, missing exact marker, missing required value, budget exhaustion or protocol violation stops the experiment.
- Do not modify Product repository, Product Skill, Wrapper, Transport, Hook or Protocol.

RETURN:
- FACTS_PROVEN
- FACTS_UNVERIFIED
- IDENTITY_SOURCE_TRUTH_TABLE
- RAW_EVIDENCE_PATHS
- REFERENCE_PROBE_PATHS
- PRODUCT_CONSTRAINTS_DISCOVERED
- TEST_PROTOCOL_VIOLATION
- EXPERIMENT_ACCEPTANCE: MET / NOT_MET / UNVERIFIED
```
