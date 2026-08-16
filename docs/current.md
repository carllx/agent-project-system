# Current Project State

## Project identity

- **Name:** Agent Project System
- **North star:** 建立一套与具体 IDE 和 Transport 解耦的 **Agent Collaboration Framework**，使 Browser Lead 与 IDE Agent 能通过可定义、可观察、可恢复、可审查、可测试的协议形成长期工作闭环。见 `docs/adr/0003-agent-collaboration-framework.md`。
- **Repository root:** `E:\PROJECTS\agent-project-system`
- **Remote:** `https://github.com/carllx/agent-project-system.git`
- **Project phase:** `USABLE / MVP-1 MAINLINE INTEGRATION`；继续适用 Maintenance policy，不主动开发或实验。
- **Active branch:** `integration/autonomous-review-loop-main`；`work/real-agent-review-loop-mvp-001` 冻结为历史 Known Good branch，不再修改。
- **Main baseline:** `7a7536701bab5855713f00dfc85a6d90e648a229`（`docs: close Antigravity completion gate work item`）。
- **Phase baseline:** `74b210fac65e1eb7681ff40f53c35714c7569681`（上一 Work Item closeout）；它不是当前 Work Item 的初始化 commit。
- **Work Item initialization commit:** `92a9661434683afd5bd8d71adaa56530040b7a19`（`docs: start real agent review loop MVP`）；它不是 Phase baseline。当前 Git HEAD 由 Git/交接消息提供，本文件不自包含其所在 commit 的 SHA。
- **Product Contract baseline:** `d73314ad44e72ea78b8729b593a1b797362c46af`。
- **Handoff checkpoint:** 由交接消息提供 exact `HANDOFF_COMMIT_SHA`；本文件不能自包含其所在 commit 的 SHA。
- **Source Skill VERSION:** `0.4.21`。
- **PROJECT_ANTIGRAVITY_RUNTIME_COPY:** `.agents\skills\research-review-lead`；由 `scripts/sync_skill_runtime.py` 从 source 单向部署，当前 VERSION `0.4.21`，九个声明文件 SHA-256 parity `PASS`。实验输入曾观察旧 runtime VERSION `0.4.14`；本轮 Product workspace 的 pre-sync 只读检查发现目标路径当时不存在，因此两项按 provenance 分开记录，不互相覆盖。
- **OBSERVED_LOCAL_INSTALL_PATH:** `C:\Users\carll\.codex\skills\research-review-lead`；目录存在，VERSION `0.4.15`，九个文件与源包逐文件 SHA-256 一致。
- **HISTORICAL_DESIGN_TARGET:** `$HOME/.agents/skills/research-review-lead`（ADR-0002）；本机当前不存在。
- **CANONICAL_DEPLOYMENT_PATH:** `UNVERIFIED`。仓库没有安装脚本；项目历史记录了 `.codex\skills` 的本机安装结果，但不能证明它是所有平台通用的 canonical Codex 用户级 Skill路径。
- **MAT_PROCESS_AUTHORITY:** 见 `docs/specs/system-governance.md#engineering-skills-and-process-authority`。

## 系统目标

Agent Project System 不是单独的 RR Lead Skill，也不是 OpenCLI Transport，而是一套与具体 IDE 和 Transport 解耦的 Agent Collaboration Framework：

```text
Agent Project System
→ Agent Collaboration Framework
→ Browser Lead / IDE Agent Collaboration Protocol
→ Runtime / Orchestration
→ Transport / IDE Adapters
```

- **Browser Lead：** 负责规划、架构、Review 与被授权范围内的技术判断；审查 Lab Evidence 后只把清理过的事实和 Work Order 交给 Product。
- **Product Agent：** 负责 Product Problem、Contract、Acceptance Criteria、implementation 与 tests；可以运行在 Antigravity、Codex 或 future IDE，只读取同一 Project Contract。
- **Lab Agent：** 只执行明确的 `LAB_EXPERIMENT_HANDOFF`，保存 raw Evidence 并返回 Reference Probe；不得直接修改 Product 或把自报 PASS 提升为产品事实。
- **用户：** 保留目标、范围、权限、风险、成本和重要产品方向的最终决定权。
- **参考 IDE 顺序：** Antigravity 为第一参考 IDE；Codex 后续用于跨 IDE 通用性验证。
- **OpenCLI：** 只是 Transport Adapter，不等于整个系统。
- **rr-lead-skill-lab：** 独立实验环境，不是正式产品源码仓库。

## 当前模块

- `skills/research-review-lead/`：已登记的正式运行模块（Minimal Browser Review Bridge），VERSION `0.4.21`。
- `skills/research-review-lead/scripts/opencli_transport.py`：Minimal Browser Review Bridge CLI facade，提供 `review-bootstrap` 与 `review`（含 `--reconcile`）。
- `skills/research-review-lead/scripts/minimal_bridge.py`：Minimal Browser Review Bridge 核心实现（Conversation binding、canonical request envelope/hashing、PREPARED/SEND_ATTEMPTED/RESPONSE_RECEIVED durability、fast submit 与 read-only reconcile）。
- 旧版 `runtime/review_loop.py`、`runtime/completion_gate.py`、`scripts/acf_review_loop.py`、`adapters/antigravity/stop_hook.py` 以及旧 transport 模块已按架构审计彻底删除。

## Active Frontier: Minimal Browser Review Bridge

- **Active Work Item:** `APS-MINIMAL-BRIDGE-008`
- **Architecture Model:** Antigravity `/goal` 拥有 IDE Agent 执行与重试的外循环；本项目只拥有精简的 Browser Review Bridge。
- **Surviving Components:** `opencli_transport.py` (CLI facade) -> `minimal_bridge.py` (Core Bridge) -> OpenCLI -> Browser.
- **Validation:** `scripts/test_minimal_review_bridge.py`；`scripts/test_check_skill_package.py`；`python scripts/check_skill_package.py`；`python scripts/check_docs.py`。
- **PR #3:** 处于 Draft / Blocked 状态，不执行自动 merge。
- **Deleted Legacy Components:** `runtime/review_loop.py`、`runtime/completion_gate.py`、`scripts/acf_review_loop.py`、`adapters/antigravity/stop_hook.py`、旧版 3986 行 transport 测试与 600 行硬门禁。
- **HISTORICAL_ONLY:** 已完成或失败的 Acceptance/Diagnostic Packets 保留为审计 Evidence；不得继续复制整份 Packet 创建新运行实例。
- **Merge gate:** 现有相关回归和文档检查通过后提交 PR #3 最终 Browser Review；本文件不自行授权 merge。

## Current Work Item Closeout

- **ID:** `REAL-AGENT-REVIEW-LOOP-MVP-001`
- **Name:** Real Agent Review Loop MVP
- **State:** `ACHIEVED`
- **Workflow state:** `COMPLETED`
- **Review Request ID:** `REAL-AGENT-REVIEW-LOOP-MVP-001-ACCEPTANCE-MANUAL-003-R2-FINAL`
- **ACTIVE_EXECUTION_PACKET_POINTER:** `docs/references/current-execution-packet.md`
- **Execution Packet state:** `COMPLETED`
- **Active Acceptance Run:** `REAL-AGENT-REVIEW-LOOP-MVP-001-ACCEPTANCE-MANUAL-003` (COMPLETED)
- **Phase baseline:** `74b210fac65e1eb7681ff40f53c35714c7569681`（`OPENCLI-SESSION-DISCOVERY-001` closeout）。
- **Transport approved artifact:** `5482df126647687c1b837bbffa56c43da3b7346d`；`FROZEN_AT_MVP_0`。
- **Objective:** 让真实 Antigravity Execution Agent 与独立 Browser GPT Supervisor 完成一次 `Execute → Review → Revise → Review → Approve` 协作循环，并且只有匹配的 Final Browser `APPROVE` 才能完成 Work Item。
- **Scope:** 选择一个安全、真实、可快速复查的小任务；建立最小 Loop Driver/状态桥接；提交 identity-bound Review Request 与 Evidence；接收并执行 Browser `REVISE`；重新 Review；把匹配的 Final `APPROVE` 映射到 Completion Gate 与 Work Item completion。
- **Out of scope:** 主动扩展 OpenCLI Transport、补证 timeout/no-extra-conversation、Codex Adapter、MCP、Plugin、通用 orchestration、UI、多 Browser Lead、并发、quorum 或长期 Hook deployment 裁决。

### Post-closeout Product integration outcome

- `DIRECT_NODE_PRODUCT_INTEGRATION` 已进入 Product source，并由 `AUTONOMOUS-BROWSER-PRODUCT-FINAL-SMOKE-001` 在 Product HEAD `cfee67dbf016d6b1c94d78f3f77ebc0eb6cd53da` 完成真实 autonomous Product loop 验证。
- `CODEBLOCK_STRICT_RR_COMPATIBILITY=PROVEN`：Automated Browser 的完整 machine RR wire 使用唯一 fenced `text` code block，OpenCLI plain extraction 后原样进入 strict parser；block 外不得有文字，不使用 Markdown converter、normalize、replace、dedent 或 repair。
- `.agents` Antigravity runtime copy 已单向同步到 authoritative Product VERSION `0.4.18`，九个声明文件 VERSION/hash parity `PASS`；`.agents` 仍是 ignored deployment artifact，不是 source。
- `AUTONOMOUS_ANTIGRAVITY_BROWSER_LOOP_VALIDATED=YES`；`PRODUCT_AUTONOMOUS_LOOP_READY_FOR_USE=YES`；`USER_MANUAL_RELAY_COUNT=0`；`HOOK_USED=NO`。本验证不重开 `REAL-AGENT-REVIEW-LOOP-MVP-001`，其状态仍为 `ACHIEVED / COMPLETED`。
- **Known-good baseline:** Product HEAD `cfee67dbf016d6b1c94d78f3f77ebc0eb6cd53da`，Conversation `6a7b4841-8188-83ea-b5cb-e15373446131`；R1 Delivery/Response identity verified 后返回 `REVISE`，Required Action 已执行，R2 在同一 Conversation Delivery/Response identity verified 后返回 `APPROVE`。结论只覆盖该 Product、environment 与 workflow，不推广到所有未来 Browser/OpenCLI 情况。

### Acceptance Criteria

1. 一个真实小任务由 Antigravity Execution Agent 在明确 Goal、Scope 与 Acceptance Criteria 下执行，不以模拟结果替代。
2. Execution Agent 生成最小 ACF-0.1 Review Request 与可复查 Evidence，并通过用户维持同一 Browser Lead Conversation 的 Manual Relay 路径保存、严格绑定和 ingest 两轮真实 Browser Decision；不声称 machine-verified Conversation identity。
3. Browser Lead 返回与 Protocol、Work Item、Request ID 和 Review Kind 匹配的 `REVISE`，且含可执行 `REQUIRED_ACTIONS`。
4. Browser Decision 被可靠带回 IDE execution state；Execution Agent 不自行批准，按 Required Actions 修订并使用新 Request ID 重新提交同类 Review。
5. Browser Lead 对修订后的 Final Request 返回权威 `APPROVE`，全部 agreed Acceptance Criteria 为 `MET`，无 unresolved User Decision。
6. Completion Gate 只在该匹配且未 stale 的 Final `APPROVE` 后允许 Work Item 完成；execution termination 不等于 Completion Authority。
7. 两轮 Manual Relay 保持不同 Request ID、raw response provenance、exact binding 与不伪造 Transport identity；automated Browser Transport 验证明确保留为未完成边界。
8. 真实 Loop Evidence、状态迁移、测试/检查与 Git artifact 可由 Browser Lead 独立复查，文档无重复 SSOT。

### Immediate execution boundary

- 先审计现有 Protocol、Completion Gate、Antigravity Adapter、RR Skill 和冻结 Transport 之间阻塞真实 Loop 的最小缺口。
- 只实现第一条真实 Loop 所必需的 bridge/driver；不得把下一阶段扩展成完整 orchestration framework。
- Browser Review 与用户权限必须继续分离；任何 IDE tool approval 不得解释为 ACF Review approval。

### Integration Gap Audit and MVP readiness

**ALREADY_AVAILABLE:** ACF-0.1 Request/Decision 与 Completion invariant；五类 Conversation identity 和冻结 Product Transport；identity-bound RR response；Completion-Gate Policy；Antigravity Stop Hook 的动态 route 与 bounded continuation。

**MINIMUM BRIDGE IMPLEMENTED:** `runtime/review_loop.py` 现在保存 pending Request snapshot 和 reviewed artifact identity，把唯一 identity-verified RR envelope 严格映射为 ACF Decision，并驱动 `FINAL_REVIEW_PENDING → REVISION_REQUIRED → EXECUTING → FINAL_REVIEW_PENDING → COMPLETED`。它同时从 pending Request 确定性渲染包含 strict RR response contract、完整 agreed AC 和 exact ACF binding 的 canonical Browser body，不再要求 Execution Agent 手工拼 message。`scripts/acf_review_loop.py` 的受限 `send-review / recover-review` 路径只使用冻结 Transport 默认预算，自动绑定 Request ID/Round/verified continuation target，并在同一 Request artifact 已存在时 fail closed。错 Protocol、Work Item、Request ID、Review Kind、Acceptance coverage、wire/ACF binding、stale artifact 或未验证 Transport response 均为 `NON_AUTHORITATIVE`，不得改变 pending Workflow State。Transport 的旧 `work_item_state=ACHIEVED` 明确不具有 Product completion authority。只有 bridge 本地推导 `REVIEWED_STATE_CURRENT` 后，现有 Completion Gate 复验 Final `APPROVE` 才能写入 `COMPLETED`。

**ANTIGRAVITY RETURN PATH:** Browser `REVISE` 被保存为单个当前 `ACTION_ID`、完整 `REQUIRED_ACTIONS`、`CURRENT_REQUIRED_ACTION` 与一次 bounded `CONTINUATION_STATE`。Antigravity Adapter 的 `decision=continue` reason 现在携带当前动作说明，真实 Execution Agent 仍必须从配置的 state path 读取权威状态。修订 Evidence 记录后回到 `EXECUTING`，重新 Review 强制使用新 Request ID 并保持原 Review Kind。

**CONFIGURATION_ONLY:** 为本次真实 MVP 填写精确 workspace、Work Item、runtime state/evidence path、经验证 Python/Stop Hook 绝对路径和可选 Antigravity Execution Conversation ID。Browser Transport Conversation 与 Antigravity Execution Conversation 必须分开。当前不裁决长期 Global 与 workspace-local Hook deployment。

**TRUE_EXTERNAL_UNKNOWN:** 无会改变最小 bridge 实现选择的外部未知量。实际 Antigravity route 触发和 Browser 对 compatibility envelope 的服从将在真实 Loop 中观察；失败时才形成直接 blocker。

**REAL_LOOP_STATE:** `MANUAL_RELAY_VALIDATED / COMPLETED`。`ACCEPTANCE-MANUAL-003` Product state 记录 R1 authoritative `REVISE`、`REQUIRED_ACTION_APPLIED`、R2 authoritative Final `APPROVE` 和两次 `MANUAL_REVIEW_INGESTED`。R2 reviewed artifact SHA-256 与 pending identity 一致；只读 Completion-Gate 复验返回 `ALLOW_STOP / work_item_completed=true`。这些 Product/runtime Evidence，而非实验 Agent 的治理声明，构成本 Work Item `ACHIEVED` 的依据。

### Manual Relay readiness

- **MANUAL_RELAY_ACCEPTANCE_READY:** `NO`；run 已完成，不得重启。
- **Available:** `initialize`、`submit-review`、`render-review-message`、`ingest-manual-review`、revision state transition 与 Completion Gate policy。
- **Validation:** raw RR sentinel/field order、Work Item/Request/Round/ACF binding、Acceptance coverage、stale artifact、REVISE action 与 APPROVE authority 均 fail closed；成功 ingest 记录 `REVIEW_SOURCE=MANUAL_RELAY`，不会写入 automated Transport identity flags。
- **Previous run:** `REAL-AGENT-REVIEW-LOOP-MVP-001-ACCEPTANCE-MANUAL` = `CLEAN_HARD_STOP / R1_MANUAL_RESPONSE_INGEST / MANUAL_RELAY_COPY_FORMAT_CORRUPTION`；`PRODUCT_PARSER_FAILURE=NO`，`BROWSER_DECISION_INGESTED=NO`，旧 runtime 不得复用。
- **Previous run:** `REAL-AGENT-REVIEW-LOOP-MVP-001-ACCEPTANCE-MANUAL-002` = `CLEAN_HARD_STOP / R2_FINAL_BROWSER_REVIEW / FINAL_ACCEPTANCE_CRITERIA_CIRCULAR_DEPENDENCY`；Transport、Manual ingest 与 parser 均未失败，R1 和 R2 `REVISE` 均为 authoritative，旧 runtime 作为 Evidence 保留但不得继续。
- **Copy-safe contract:** Manual renderer 使用 `BROWSER_RESPONSE_PRESENTATION=COPY_SAFE_PLAIN_TEXT_BLOCK`；用户只使用独立 block 的 copy control，raw wire 不含 fence，顶层字段保持 column zero，并建议在最后一项 Acceptance Evidence 与 `FINDINGS:` 之间留空行。Parser strictness 不变。
- **Two-gate contract:** Gate A 仅含 Browser 输出当前 Decision 前已经存在并可审查的事实；Gate B 在 Final response 保存/ingest 后，由现有 Product state、Manual provenance 与 Completion Gate 验证。Gate B 失败为 `POST_INGEST_COMPLETION_FAILURE`，不得倒改 Browser 历史 Decision。
- **Manual-003 verified:** R1 raw SHA-256 `98cf130d5ba507d646d48e011577862ca7c32570453c95f5a65bd5e6114f00ad`；R1 artifact SHA-256 `e08d9ad1d1867d0982dcdae387b54c65e89c07d2688ec1c2d974d385d68ebc0f`；R2 raw SHA-256 `b9e2981a9738421d7e7025646a850b8b2818b22942726697491564b7e2d6e0c5`；R2/current artifact SHA-256 `62196d412c338988c9d1a51fb09746af61ad82c2c63a2d14453ba4268ea08dcf`。
- **Final outcome:** `REAL_AGENT_REVIEW_LOOP_FUNCTIONALLY_VALIDATED=YES`；`MANUAL_RELAY_VALIDATED=YES`；`AUTONOMOUS_ANTIGRAVITY_BROWSER_LOOP_VALIDATED=YES`；`PRODUCT_AUTONOMOUS_LOOP_READY_FOR_USE=YES`；`COLLABORATION_MVP_USABLE=YES`。
- **Boundary:** Manual Relay 与当前 Direct Node automated Product path 均已验证；Windows `.cmd` / observed long-argv failure record 仍保留，但不阻塞当前 known-good Direct Node path。结论只覆盖已验证 Product/environment/workflow，不证明所有未来 Browser/OpenCLI 状态。

### Attempt 4 canonical closeout

```text
ATTEMPT_ID: ATTEMPT-4
ATTEMPT_RESULT: CLEAN_FAIL
PROTOCOL_VIOLATION: NO
ROUND_1_WRITE_COUNT: 1
RESEND_PERFORMED: NO
FINAL_TRANSPORT_CLASSIFICATION: DELIVERY_UNKNOWN
PRIMARY_OBSERVED_BLOCKER: OpenCLI send returned non-success after /new preparation, and exact Delivery Conversation identity could not be established.
ROOT_CAUSE: PRE_WRITE_AND_POST_WRITE_VERIFICATION_SHARE_ONE_OPERATION_BUDGET
ROOT_CAUSE_PROVEN: YES
```

`DELIVERY_UNKNOWN` 不等于 `FAILED`。Evidence 证明的是 H6：首次 post-write Browser identity observation 仍处于 pre-write/send operation，因而在 dedicated navigation wait 可靠介入前已被剩余 operation timeout clamp。H4/H5 未被升级为已证明根因。

### Diagnostic closeout and next Acceptance Run

- **BATCH_ID:** `REAL-AGENT-REVIEW-LOOP-MVP-001-DIAG-BATCH-001`
- **Diagnostic state:** `COMPLETED / ROOT_CAUSE_PROVEN`
- **Result:** `H6=PROVEN`；`ROOT_CAUSE=PRE_WRITE_AND_POST_WRITE_VERIFICATION_SHARE_ONE_OPERATION_BUDGET`；采用 `MODIFIED_OPTION_C`，在 write 调用返回后、首次 post-send status 前开始独立 bounded `POST_SEND_VERIFICATION` operation。
- **Product authority:** `E:\PROJECTS\agent-project-system`。
- **Lab environment:** `E:\PROJECTS\rr-lead-skill-lab`。
- **Active Packet:** 新的 canonical multi-turn Acceptance Packet 由 `docs/references/current-execution-packet.md` 唯一指向，状态 `READY / NOT_STARTED`；本轮不执行真实 Browser write。
- **Boundary:** 本 Batch 属于当前 Work Item，不创建并行 Active Work Item；未来 `ANTIGRAVITY-BOUNDED-EXPERIMENT-BATCH-MVP-001` 仍为 `NOT_ACTIVE` 候选。

### Local integration validation

- Acceptance bootstrap governance：active pointer、Packet SHA-256、Work Item 与 exact Product head 由 `check_docs.py` 一致性校验；fresh Coordinator 路径为 `AGENTS.md → docs/current.md → pointer → Packet`。
- Review Loop + Completion Gate suites：29/29 PASS；包含 canonical renderer → Transport preflight integration regression。
- Transport suite：200/200 PASS；包含旧路径接近 60 秒时 status timeout clamp、新 operation 首次 status 获得正常 bounded timeout、timeout/nonzero send 仍进入 verification 且不重发、navigation bounds、canonical receipt 与 same-ID no-resend。
- Real Agent Review Loop suite：19/19 PASS；未把本地 suite 写成真实 Browser Final `APPROVE`。
- Package checker unit suite：14/14 PASS。正式 package checker 的字母排序 runner 两次分别在不同既有 Transport fixture 上失败；两项失败测试均立即单独 PASS，完整 197-test suite PASS。精确 runner failure cause 未证明，因此只记录为 package-runner-only intermittent failure，不升级为 Product Transport failure，也不放宽任何 runtime/test budget。
- Package checker unit suite：14/14 PASS。完整 `check_skill_package.py` 的隔离 Transport subprocess 在既有 240 秒 runner 上限处 timeout；同一 194-test suite 已独立全绿。本 Work Item 不为此放宽 Transport 或 checker timeout。
- `check_docs.py` 与 `git diff --check`：PASS。
- 尚未运行真实 Antigravity/Browser E2E；不得把本地测试写成 Browser `APPROVE`。

## Latest Completed Work Item: OPENCLI-SESSION-DISCOVERY-001

- **ID:** `OPENCLI-SESSION-DISCOVERY-001`
- **Name:** OpenCLI Session Discovery and Identity Contract
- **State:** `ACHIEVED`
- **Workflow state:** `COMPLETED`
- **Review Request ID:** `OPENCLI-SESSION-DISCOVERY-001-MVP0-R2-FINAL`
- **Main baseline:** `7a7536701bab5855713f00dfc85a6d90e648a229`。
- **Product Contract baseline:** `d73314ad44e72ea78b8729b593a1b797362c46af`（供 `OPENCLI-SESSION-IDENTITY-MIN-001` Lab 实验绑定）。
- **Objective:** 建立 `CREATE → CAPTURE → VERIFY → SEND → VERIFY DELIVERY → RECOVER` 的 Session Discovery / Identity Contract，并据此修复 Product Transport 对 Conversation identity 的建立、验证、错投检测与 bounded recovery。
- **Scope:** 现有 OpenCLI Transport 与历史 Evidence 审计；五类 identity、Evidence、状态和 no-resend Contract；Product Acceptance Criteria；真正未知机制的最小 Lab handoff；后续在 Evidence 基础上的 Product implementation 与 regression tests。
- **Out of scope:** 重测普通 send/receive、修改 ACF-0.1、Hook、Completion Gate、Antigravity deployment、MCP、Plugin、GitHub automation、无界 Browser 调试或让 Lab 直接成为 Product source。

### Session identities

- `CREATED_CONVERSATION_ID`: 创建动作直接建立并证明的 identity；`/new`、根页面和 `EMPTY_RESULT` 不等于 ID。
- `TARGET_CONVERSATION_ID`: 写入前绑定的预期目标。
- `CURRENT_BROWSER_CONVERSATION_ID`: 某次 status 中精确 `/c/<id>` 页面，只证明当时 Browser 位置。
- `DELIVERY_CONVERSATION_ID`: exact Work Item/Message marker 证明的实际投递位置。
- `RECOVERED_CONVERSATION_ID`: timeout/缺失身份后 bounded recovery 选出的唯一候选；只有 marker 验证后才可成为 delivery identity。

完整 Contract、已知/未知事实、Acceptance Criteria 与 `LAB_EXPERIMENT_HANDOFF` 的唯一权威为 `docs/specs/opencli-session-discovery.md`。

### Lab R2 technical evidence

- **Experiment:** `OPENCLI-SESSION-IDENTITY-MIN-001-R2`；raw provenance `E:\PROJECTS\rr-lead-skill-lab\evidence_OPENCLI-SESSION-IDENTITY-MIN-001-R2.md`，仅为外部 Evidence Source。
- `NEW_SESSION_PRE_SEND_EXACT_ID=NOT_AVAILABLE / PROVEN`。
- `NEW_SESSION_FIRST_WRITE_IDENTITY_CAPTURE=PROVEN`。
- `FIRST_DELIVERY_CONVERSATION_ID=6a782fe4-b7b4-83ea-a299-765d1ef80e89`。
- `PROMOTED_TARGET_CONVERSATION_ID=6a782fe4-b7b4-83ea-a299-765d1ef80e89`。
- `SECOND_DELIVERY_CONVERSATION_ID=6a782fe4-b7b4-83ea-a299-765d1ef80e89`。
- `NEW_SESSION_MULTI_ROUND_SAME_DELIVERY_CONVERSATION=PROVEN`。
- 已证明最小机制：`/new → first write once → post-send exact identity capture → exact marker verification → promote delivery as next target → subsequent write --conversation <TARGET> → same-delivery marker verification`。
- `read` 仍是 current-page-bound，不是 arbitrary exact-ID read；explicit-target write 会导航 Browser 到目标 Conversation。

### Lab protocol debt and unverified facts

- `TECHNICAL_HYPOTHESIS_RESULT=PROVEN`，但 `TEST_PROTOCOL_VIOLATION=YES`、`EXPERIMENT_PROTOCOL_COMPLIANCE=NOT_MET`：可见 Agent trace 出现两次 `schedule`，违反 `MAX_SCHEDULE_CALLS=0`。Lab 原报告中的 `TEST_PROTOCOL_VIOLATION=NO / EXPERIMENT_ACCEPTANCE=MET` 不作为 Product 事实。
- `NO_EXTRA_CONVERSATION_CREATED=UNVERIFIED`：缺少 bounded post-write history delta。
- `TIMEOUT_RECOVERY=UNVERIFIED`：本轮没有自然 timeout/navigation error；不得为了补证故意制造 timeout。
- protocol violation 不自动抹除 independently observed identity Evidence；技术结论与实验合规分开记录。

### Reliable Product Transport MVP-0

- Product write 已切换为 `opencli chatgpt send`；new-session first write 不带 target，existing-target continuation 使用 `send --conversation <TARGET_CONVERSATION_ID>`。
- 每次 write 后都捕获 status/current page，并只在 current-page read 或 bounded exact detail 中出现唯一 exact `WORK_ITEM_ID + MESSAGE_ID` marker 时建立 `DELIVERY_CONVERSATION_ID`。OpenCLI 返回的 identity 只作候选 observation。
- Runtime schema v5 显式承载五类 identity、`target_conversation_id_at_send`、binding mode、append-only observations 与 establishment provenance；legacy delivery/recovery identity 迁移时只保留为候选，不重置发送计数。
- 已保护 same Message ID 最多一次 write、`DELIVERY_UNKNOWN != FAILED`、target/delivery mismatch 为 `MISROUTED_DELIVERY`、missing/duplicate/conflicting identity 不得提升 delivery/target。
- 新增 25 项原生 MVP regression，并保留既有 169 项回归；当前完整 suite 为 194 项。其中包括 canonical write receipt 跨 state-file 防重、existing target 优先 recovery、写后 budget exhaustion/Manual Export 不得导致同 ID relay、timeout+marker recovered provenance、create-result validation，以及 bounded post-send navigation success/deadline/attempt exhaustion/actual status error/conflict/marker ambiguity/no-resend。

### Next immediate action

`TRANSPORT_IMPLEMENTATION_READY=YES`、`TRANSPORT_REGRESSION_READY=YES`、`TRANSPORT_REAL_E2E_VALIDATED=YES`：Product implementation 已把 `POST_SEND_NAVIGATION_WAIT` 修正为最多 30 秒、最多 10 次 status 的独立只读 phase。旧 9-command 与 60-second operation budget 数值不变；navigation elapsed 从旧 operation budget 显式排除，使 qualifying operation 的物理 wall-clock 最多增加 30 秒。write/recovery/detail budget均未改变。完整 194 项 Transport/Product regression 与真实两消息同 Conversation E2E 均通过。Transport 主动开发停止并保持冻结；`NO_EXTRA_CONVERSATION_CREATED` 与真实自然 timeout recovery 保持 `UNVERIFIED`。

`NEXT_PRODUCT_ACTION_CANDIDATE`：启动一次真实 Agent Review Loop MVP，把现有 ACF Review Contract、Review Artifact、冻结的 RR Transport、Browser Decision、revision execution 与 Completion Gate 串成 `Execute → Review → Revise → Review → Approve`。

Browser Final `REVISE` 指出的 first-write 前 blocker 已归类为 `PRODUCT_VALIDATION_BUG`：旧实现错误地把 `new` command result row 当成继续验证的前置条件，而真正的 write gate 应是 post-new exact status `/new`（或 root）与 empty read。最小修复已完成并由两条新增 regression 覆盖。

Browser-cleaned R3 Evidence 到位并实现 navigation wait 后，只运行了一次新的 bounded Product E2E。Message 1 使用 repository source `0.4.17` 与全新 Message ID；`new` command 在 15 秒 local wait 内 timeout，但后续 exact status `/new` 与 empty read 建立 blank-page write gate；`send` 返回 0/`Success` 且写入计数为 1。真正的 starvation 发生在 navigation wait 之前：首次 `capture_post_send_status()` 仍调用受 pre-write/send operation 剩余时间 clamp 的 `command()`。因此不能表述为“30 秒 navigation budget 缩到 2.63 秒”；准确根因是 `PRE_WRITE_AND_POST_WRITE_VERIFICATION_SHARE_ONE_OPERATION_BUDGET`。最终仍为 `DELIVERY_UNKNOWN` 且禁止同 ID resend；Message 2 未启动。

独立 navigation phase revision 后只运行了一次新的 bounded Product E2E。Message 1 使用 repository source `0.4.18` 与全新 Message ID，write count `1`；immediate status 为 `/new`，随后两次只读 status 在 `6.875` 秒内观察到 Conversation `6a79d6d2-cab8-83ea-9081-9604dfabd39d`。唯一 exact marker 经 bounded detail 验证后建立 Delivery A，并把 A 提升为下一 Target。Message 2 使用另一全新 Message ID 与 `send --conversation A`，write count `1`；post-send status/current-page read 的唯一 marker 再次建立 Delivery A。两条消息均未重发，`TRANSPORT_REAL_E2E_VALIDATED=YES`。

### Intermediate Browser Review

- **R1:** `APPROVE`；`PROTOCOL_VERSION=ACF-0.1`，`IN_REPLY_TO_REVIEW_REQUEST_ID=OPENCLI-SESSION-DISCOVERY-001-R1-INTERMEDIATE`，`REVIEW_KIND=INTERMEDIATE`。
- **MET:** `AC1`、`AC2`、`AC5`、`AC6`、`AC7`、`AC9`、`AC10`。
- **At R1:** `AC3`、`AC4` 为 `UNVERIFIED`；随后 Browser 对 `OPENCLI-SESSION-IDENTITY-MIN-001-R2` 的审查已接受相关 technical Evidence，当前状态见下方 `Current Acceptance status`。
- **R1 时的 NOT_MET:** `AC8` 当时尚未开始 Product implementation/tests；本轮 MVP-0 implementation 与 regression 已完成，最终 Evidence 以本次 Review Request 为准。
- **REQUIRED_ACTIONS / DEBT / USER_DECISION_REQUIRED:** `NONE`。
- 本次 Intermediate `APPROVE` 只授权 Contract 进入 Lab validation，不批准 Work Item 完成。

### Acceptance Criteria

1. 五类 Conversation identity 在 Product Contract 与 Runtime State 中显式区分，来源和建立时点可审查。
2. `CREATE → CAPTURE → VERIFY → SEND → VERIFY DELIVERY → RECOVER` 每一步的输入、成功证据与失败语义明确。
3. 新 Conversation exact-ID 机制由现有 Evidence 或最小 Lab 实验证明；未证明时阻止需要 pre-send target 的正式发送。
4. 发送前 target 绑定与 Browser current/target mismatch 检测明确。
5. Delivery identity 只由 identity-bound exact Work Item/Message marker Evidence 建立。
6. timeout、identity conflict、misroute、recovery 与 `DELIVERY_UNKNOWN` 的迁移明确且有界。
7. 每个 Message ID 最多一次写入，delivery unknown/misroute/recovery failure 禁止 resend。
8. Product implementation 与 regression tests 覆盖正常、错页、缺失、冲突、恢复、marker ambiguity 与 no-resend。
9. 不改变 ACF Completion Authority，不把 OpenCLI、GitHub 或 Browser 当前标签提升为 authority。
10. Lab 只验证未知 Session mechanism，文档无重复 SSOT。

### MVP-0 Review readiness

- **Final state:** `ACHIEVED`；Browser Lead 对匹配的 Final Review Request 返回 `APPROVE`，Execution Agent 未自行批准。
- **Implementation:** `MET`；正式 write 为 `send`，五身份/provenance、唯一 marker、target promotion、existing target recovery 和 canonical no-resend receipt 已实现。
- **Regression:** 194/194 Transport/Product regression 与 24/24 completion-gate/package-checker regression PASS。Skill package checker 的受控 runner 继续使用 240 秒 execution timeout。Transport 普通 9-command、60-second operation、write/recovery/detail budget数值未放宽；navigation status 使用独立最多 30 秒、最多 10 次的 phase budget。
- **Transport readiness:** `TRANSPORT_IMPLEMENTATION_READY=YES`；`TRANSPORT_REGRESSION_READY=YES`；`TRANSPORT_REAL_E2E_VALIDATED=YES`。
- **Product E2E:** `PASS`；Message 1/2 各 write 一次，Delivery 与 promoted Target 均为 `6a79d6d2-cab8-83ea-9081-9604dfabd39d`，两条 exact marker 均为 `UNIQUE`。
- **Direct blocker revision:** `NAVIGATION_SUB_BUDGET_STARVED_BY_OPERATION_CAP` 已修复，并由 regression 与真实 delayed-navigation E2E 证实不再阻塞正常路径。
- **Known unverified:** `NO_EXTRA_CONVERSATION_CREATED`、真实自然 timeout recovery。
- **Work Item state:** `ACHIEVED`；Transport scope 为 `FROZEN_AT_MVP_0`，不得继续主动开发。

### Current Acceptance status

- **MET:** `AC1`、`AC2`、`AC3`、`AC4`、`AC5`、`AC6`、`AC7`、`AC8`、`AC9`、`AC10`。
- **Transport scope:** `FROZEN_AT_MVP_0`；真实 Product Browser 两消息 E2E 已 PASS，不再主动扩展 Transport。
- `OPENCLI-SESSION-DISCOVERY-001=ACHIEVED`；完成权来自下述匹配的 Browser Final `APPROVE`，不是 Lab technical hypothesis 或 Execution Agent 自批。

### Final Browser Review

- **PROTOCOL_VERSION:** `ACF-0.1`。
- **IN_REPLY_TO_REVIEW_REQUEST_ID:** `OPENCLI-SESSION-DISCOVERY-001-MVP0-R2-FINAL`。
- **REVIEW_KIND / DECISION:** `FINAL / APPROVE`。
- **APPROVED_COMMIT:** `5482df126647687c1b837bbffa56c43da3b7346d`。
- **ACCEPTANCE_STATUS:** `AC1` 至 `AC10` 全部 `MET`。
- **WORK_ITEM_STATE:** `ACHIEVED`。
- **DEBT / USER_DECISION_REQUIRED:** `NONE`。
- **NON-BLOCKING UNVERIFIED:** `NO_EXTRA_CONVERSATION_CREATED`、`TIMEOUT_RECOVERY`；未来没有新 Evidence 时不得升级。
- **Completion authority:** Browser Lead 的 Decision 与当前 pending Final Request、Protocol、Work Item、Review Kind 和获批 artifact identity 匹配，因此授权从 `FINAL_REVIEW_PENDING` 进入 `COMPLETED`。

### Review artifact access path

- GitHub 可用且 Browser 有权访问时，Review Request 优先携带 repository、Review Branch、Commit SHA 与适用的 baseline SHA，Browser 直接审查真实代码和 Diff。
- GitHub 只是 Review Artifact access path，不是 Completion Authority、ACF Protocol 或实时 Transport；无 GitHub 时继续使用 Evidence Packet / Manual Relay。
- 通用规则记录在 `docs/specs/agent-collaboration-protocol.md`；RR-specific 映射记录在 `docs/specs/research-review-loop.md`。

## Completed Work Item: ACF-AG-ADAPTER-001

- **ID:** `ACF-AG-ADAPTER-001`
- **Name:** Antigravity Completion-Gate Adapter v0.1
- **State:** `ACHIEVED`
- **Workflow state:** `COMPLETED`
- **Review Request ID:** `ACF-AG-ADAPTER-001-R2-FINAL`
- **Protocol baseline:** `ACF-0.1`，已完成并获 Browser Lead Final `APPROVE`。
- **Product baseline:** `af5d84afe314efaf9ee7bd2ad6080a032026a00d`。
- **Objective:** 把 Lab 已验证可行的 Antigravity Stop Hook、ACF Workflow State、bounded continuation 与 Final Review authority 纳入正式产品架构，形成第一版 Antigravity Completion-Gate Adapter。
- **Scope:** Product 状态、Adapter Spec/Contract、Antigravity Stop Hook 正式实现及本地测试、ADR、最小 Lab Evidence provenance 与验证。
- **Out of scope:** 修改 ACF-0.1 Protocol、复制 Lab Prototype、重跑 Hook/Browser 实验、修改 OpenCLI Transport、写入用户级 Hook 配置、Plugin、MCP、CLI、SDK 或部署裁决。

### Evidence baseline

- `ANTIGRAVITY_STOP_ADAPTER_FEASIBILITY=PROVEN`：Antigravity 2.6.0 Global Stop Hook 已真实触发；stdin 已观察到 `conversationId`、`workspacePaths`、`executionNum`、`terminationReason`、`fullyIdle`；返回 `decision=continue` 后，同一 Conversation 从 `executionNum=0` 自动恢复到 `executionNum=1`，无需用户追加消息或 `/goal` wrapper。
- `ACF_COMPLETION_GATE_REVISION_CONTINUATION=PROVEN`：当 `WORKFLOW_STATE=REVISION_REQUIRED` 且 `FINAL_APPROVAL_VALID=false` 时，Stop Hook 已拦截自然停止、执行 bounded continue，并使 Agent 恢复执行 Browser `REQUIRED_ACTIONS`。
- `OPENCLI_TRANSPORT=DELIVERY_UNKNOWN / BLOCKED`：Transport 是独立问题，不阻塞 Completion-Gate Productization。
- **仍未证明：** 真实 DeepSeek 等第三方模型 premature-stop occurrence 的恢复、workspace-local Hook 部署的最终选择、stale approval enforcement。
- **Lab provenance:** Bundle 使用 `EXPERIMENT_ID=ACF-AG-HOOK-GLOBAL-ANCHORED-005`；本机实际 Evidence 目录名为 `ACF-AG-HOOK-GLOBAL-ANCHORED-V260-005`，路径 `E:\PROJECTS\rr-lead-skill-lab\experiments\ACF-AG-HOOK-GLOBAL-ANCHORED-V260-005\`。系统实验为 `E:\PROJECTS\rr-lead-skill-lab\experiments\ACF-AG-COMPLETION-GATE-SYSTEM-001\`。Lab 是外部 Evidence Source，不是产品实现源码；标签与目录名差异不据此擅自归一化。

### Acceptance Criteria

1. Completion Authority 与 execution termination 明确解耦。
2. Protocol、Workflow State、Completion-Gate Policy、Antigravity Adapter、Stop Hook 与 Transport 边界明确。
3. `EXECUTING / REVISION_REQUIRED / INTERMEDIATE_REVIEW_PENDING / FINAL_REVIEW_PENDING / WAITING_FOR_USER / COMPLETED` 的 Stop 行为明确。
4. 只有满足 ACF-0.1 权威绑定、全部 Acceptance Criteria 为 `MET`、无 unresolved User Decision 且批准未 stale 的 Final `APPROVE` 才能进入 `COMPLETED`。
5. bounded continuation 有明确预算、重置条件和耗尽行为，不能无限唤醒。
6. Adapter 输入、输出与失败/降级语义最小且已由无 Lab 硬编码的正式实现覆盖。
7. Product 文档保存最小 Lab Evidence provenance，并区分已证明与未证明行为。
8. DeepSeek premature stop、Transport、Deployment 三项后续验证明确且不阻塞本 Work Item。
9. 不修改 ACF-0.1 Protocol，不复制 Lab Prototype，不实现 Transport；Hook 实现只承担 Antigravity runtime translation。
10. 文档无重复 SSOT，并通过仓库文档检查。

### Final Browser Review

- **R1 FINAL REVIEW:** `REVISE`；修复 pending agreed Acceptance Criteria 与 Decision coverage 未做完整、唯一、精确身份验证的问题。
- **R2 FINAL REVIEW:** `APPROVE`；`PROTOCOL_VERSION=ACF-0.1`，`IN_REPLY_TO_REVIEW_REQUEST_ID=ACF-AG-ADAPTER-001-R2-FINAL`，`REVIEW_KIND=FINAL`。
- **ACCEPTANCE_STATUS:** `AC1` 至 `AC10` 全部 `MET`。
- **REQUIRED_ACTIONS:** `NONE`。
- **KNOWN_RISKS:** Lab evidence 仍位于独立实验目录；产品仓库只保存最小 provenance 和解释，不把外部路径误写成产品实现。
- **UNVERIFIED:** DeepSeek premature-stop、stale approval enforcement、Global 与 workspace-local Hook 部署选择。
- **OPEN_QUESTIONS:** 无阻塞当前设计的问题；三项未验证内容均作为后续 Issue/Validation 保留。
- **Completion authority:** Browser Lead 已在用户授权与 agreed Acceptance Criteria 范围内批准技术完成；Execution Agent 未自行批准。

## Previous Completed Work Item

- **ID:** `ACF-PROTOCOL-001`
- **Name:** Agent Collaboration Protocol Candidate v0.1
- **Protocol version:** `ACF-0.1`
- **Review decision:** `APPROVE`
- **Work Item state:** `ACHIEVED`
- **Baseline commit:** `388245228d0455653c6d58fd26b212a5d31c598c`
- **Prerequisites:** `BOOTSTRAP-MANUAL-RELAY-001=ACHIEVED`；`LAB-REPO-REVIEW-001=ACHIEVED`。
- **Objective:** 只定义足以支持下一阶段真实实验的通用 Review Protocol，使 Execution Agent 与 Browser Lead 能执行 `Execute → Review → Revise → Review → Approve`，并禁止 Execution Agent 自行批准 Work Item 完成。
- **Scope:** Protocol v0.1、独立 Spec、RR-specific 映射说明、文档验证。
- **Out of scope:** Hook、OpenCLI Transport、MCP、Plugin、Lab Harness、Browser/Antigravity 实验。

### Acceptance Criteria

1. 明确 Intermediate 与 Final Review 的区别。
2. Execution Agent 不能 self-approve completion。
3. Review Request 有最小稳定 Contract。
4. Browser Decision 有最小稳定 Contract。
5. `APPROVE / REVISE / ESCALATE_TO_USER` 行为明确。
6. User Authority 边界明确。
7. Protocol 不依赖 OpenCLI。
8. Protocol 不依赖 Antigravity-specific schema。
9. 能被下一阶段 Lab 转化为可证伪 Hypothesis。
10. 文档不存在重复 SSOT。

### Final Browser Review

- `PROTOCOL_VERSION: ACF-0.1`
- `IN_REPLY_TO_REVIEW_REQUEST_ID: ACF-PROTOCOL-001-R3-FINAL`
- `REVIEW_KIND: FINAL`
- `REVIEW_DECISION: APPROVE`
- 所有 agreed Acceptance Criteria 已满足。
- 批准含义：ACF Protocol v0.1 已达到可交给 Lab 做第一轮真实可证伪实验的设计基线。
- 本次批准不表示 Antigravity Adapter、Stop Hook 或 Transport integration 已验证，也不表示 ACF 已产品化完成。
- 本条描述的是 `ACF-PROTOCOL-001` 收口当时；当前 Active Product Work Item 见本文顶部的 `OPENCLI-SESSION-DISCOVERY-001`。

## Earlier Completed Work Item

- **ID:** `BOOTSTRAP-MANUAL-RELAY-001`
- **Name:** 确定性 Browser Bootstrap 与 Manual Relay fallback
- **Review decision:** `PASS_WITH_DEBT`
- **Work Item state:** `ACHIEVED`
- **Skill version:** `0.4.14` → `0.4.15`
- **安装状态（本地事实）：** `OBSERVED_LOCAL_INSTALL_PATH` 存在且与源包一致；不据此声明 canonical 部署路径。

### Acceptance 状态

- **MET（本 Work Item 已完成）：**
  - `SOURCE_PACKAGE_TESTED=true`
  - `DETERMINISTIC_BOOTSTRAP_IMPLEMENTED=true`（本地全绿；真实 Browser 未验）
  - `MANUAL_RELAY_IMPLEMENTED=true`（本地全绿）
  - `OBSERVED_LOCAL_INSTALLATION=true`（本机 `.codex\skills` 副本 VERSION `0.4.15`，九文件清单与源包逐项匹配；不等于 canonical path 已证明）
- **TRANSFERRED_TO_ACF_SYSTEM_TEST（经用户批准转移）：**
  - `DISCOVERY`
  - `0.4.15 RR_REVIEW live envelope`
  - `same-Conversation two-round integration`
  - `final live collaboration smoke`
- **旧 Transport 历史（不再重复实验）：**
  - `LIVE_TRANSPORT_DELIVERY_VERIFIED=true`（已由 `FIRST-USE-LOOP-001` 与过往 Live ACK 证明“OpenCLI 能收发”，不再单独重复）。

### 用户批准的验证策略调整（2026-08-08）

不再单独为了证明 OpenCLI 能收发而重复实验。剩余 Live Gate（Discovery、RR_LEAD_PROTOCOL_VERIFIED、TWO_ROUND_SMOKE_VERIFIED、LIVE_SMOKE_TEST_PASSED）合并到后续第一轮真实 Agent Collaboration System Test 中完成，验证完整闭环：

```text
IDE Agent → Browser Review → Decision → IDE Execution → Evidence → Browser Result Review
```

这些责任没有被删除，也没有被伪造为 PASS；经用户批准，它们已从 `BOOTSTRAP-MANUAL-RELAY-001` 转移到后续 ACF System Test 的验收范围。转移后，本 Work Item 不再存在属于自身的未满足 Acceptance Criterion，因此以 `PASS_WITH_DEBT / ACHIEVED` 收口。

## 已证明能力

- 真实 RR Loop 两轮闭环成功：`FIRST-USE-LOOP-001`，`FIRST_USABLE_VERSION: 0.4.14`，最终 Browser 判定 `PASS / ACHIEVED`；无重发、无用户复制、无 push。
- 确定性 bootstrap：Wrapper 读取 init+context 文件，去除 UTF-8 BOM、统一换行、发送前拒绝非法 UTF-8/孤立 surrogate，按固定顺序与唯一边界组装；manifest 含字节数/字符数/行数/SHA-256；复用现有 send + bounded recover，同一 Message ID 只发一次。
- manual-export / `MANUAL_RELAY_REQUIRED`：不调用 OpenCLI、不建 Conversation、不增 send count、Work Item 保持 `IN_PROGRESS`；导出 hash 与准备发送正文一致。
- 严格结构化 RR_REVIEW 解析、身份绑定、同 Message ID 禁重发；纯本地 Transport 回归 169 项全部通过，checker unittest 14/14。
- `LIVE_TRANSPORT_DELIVERY_VERIFIED=true`（旧历史证明 Transport 能收发；不再重复实验）。

## 已转移的系统级验收

- Discovery、0.4.15 RR_REVIEW live envelope、same-Conversation two-round integration 与 final live collaboration smoke 由后续 ACF System Test 验收。
- 在该系统测试完成前，不声明这些 transferred criteria 为 PASS。

## Blocker / Debt

- **Blocker：** 无。
- **Debt（不阻止旧 Work Item 完成）：** 后续证据应区分 `PROBE_CONVERSATION_ID` 与 `RR_LOOP_CONVERSATION_ID`，避免把独立探针 Conversation 误写为当前 Loop Conversation。

## 后续 Issue / Validation

- `VALIDATION_CANDIDATE: THIRD_PARTY_PREMATURE_STOP`：验证真实 DeepSeek 等第三方模型异常停止是否进入同一 Stop lifecycle 并可由 Adapter 恢复。
- `PRODUCT_CANDIDATE: CODEX-COMPLETION-GATE-ADAPTER`：为 Codex 寻找可验证的 runtime/lifecycle mechanism，并映射同一 IDE-independent Completion-Gate Contract；`NOT_STARTED`，不阻塞 Session Discovery。
- `VALIDATION_CANDIDATE: OPENCLI_TIMEOUT_RECOVERY`：只观察未来合法 Product flow 自然出现的 timeout/navigation error；不为制造 timeout 增加 write、poll、sleep、网络干扰或 Browser manipulation。
- `DECISION_CANDIDATE: ANTIGRAVITY_HOOK_DEPLOYMENT`：另行裁决 Global Hook 与 workspace-local Hook 的产品部署形式。
- `NEXT_REQUIREMENT_CANDIDATE: ANTIGRAVITY-BOUNDED-EXPERIMENT-BATCH-MVP-001`：边界见下节；真实 Agent Review Loop 的完成前置条件已满足，但仍须 Browser Lead 另行决定是否激活。
- 以上候选均保持 `NOT_ACTIVE`；本次收口没有启动新的 Active Work Item。

### Next Requirement Candidate: Antigravity Bounded Autonomous Experiment Batch MVP

- **ID:** `ANTIGRAVITY-BOUNDED-EXPERIMENT-BATCH-MVP-001`。
- **State:** `NEXT_REQUIREMENT_CANDIDATE / NOT_ACTIVE`。
- **Activation gate:** `REAL-AGENT-REVIEW-LOOP-MVP-001` 的真实 `Execute → Final Review → REVISE → Revision → Final Review → APPROVE` 前置条件已满足；本候选仍为 `NOT_ACTIVE`，只有 Browser Lead 后续明确决定才可激活。
- **Problem:** 当前 Lab 常以单个小实验往返 Browser，启动与协调成本过高。候选目标是在一个显式有界的 Experiment Batch 内，让 Antigravity Experiment Coordinator 连续选择并执行若干可归因实验，最后一次性向 Browser Lead 汇报。
- **First-version proof target:** 一个 Antigravity Experiment Coordinator 能在一个 bounded Batch 内自主完成若干有因果可归属的实验，保留完整 Evidence chain；不以此证明通用 orchestration 或替代 Browser supervision。

关键架构边界：

```text
INTERNAL ANTIGRAVITY LOOP
Experiment Coordinator ↔ Sub-Agents ↔ Runtime Experiment

EXTERNAL SUPERVISION LOOP
Browser Lead ↔ Antigravity Experiment Coordinator
```

External Loop 仍属于正在验证的 Product 能力，不得成为 Internal Batch 的假定可靠基础设施。内部自主循环必须在 Browser 预先给定的 Batch Contract 内独立有界终止。

并行硬原则为 `Cognitive work parallel; shared Runtime mutation serial`。Hypothesis design、static investigation、environment/evidence audit、result analysis 和 counter-hypothesis review 可并行；Antigravity Session、Conversation identity、Global/workspace Hook、`hooks.json`、Runtime/Workflow State、shared Evidence path、Stop/Resume lifecycle 等无法物理隔离的共享资源必须串行。未来 Contract 使用最小 resource classification：`READ_ONLY / ISOLATED_MUTATION / SHARED_RUNTIME_SERIAL`；只有前两类在实际隔离成立时允许并行。

Experiment Coordinator 是 Batch 唯一决策整合者。它可按需调用 Hypothesis、Environment/Evidence Audit、Runtime Experiment、Evidence Analysis、Counter-Hypothesis/Reviewer 等 Sub-Agent，但不得机械固定数量。Coordinator 负责合并 Evidence、判断 attribution、选择下一实验、控制全部 hard budget 并形成唯一 Batch Final Output。

每个 Batch 启动前必须固定：

```text
BATCH_ID
OBJECTIVE
UNKNOWN_SET
INITIAL_HYPOTHESES
MAX_EXPERIMENTS
MAX_ROUNDS
MAX_RUNTIME_WRITES
MAX_SHARED_STATE_MUTATIONS
MAX_WALLCLOCK
ALLOWED_ACTIONS
FORBIDDEN_ACTIONS
STOP_CONDITIONS
```

内部循环可执行 `Hypothesis → Prepare → Execute → Evidence → Classify → Analyse → Select Next Experiment`，但不得改变上述 hard Contract。Mandatory Stop 至少覆盖：hypothesis 明确 `PASS/FAIL`；新未知要求改变 Batch Contract；Evidence attribution 无法确定；共享环境污染；需要架构改变或人工操作；下一实验可能破坏有效 Evidence；任一 hard action budget、experiment、round 或 wall-clock 上限耗尽。

每个 Experiment 的最小 Evidence chain 为：`EXPERIMENT_ID`、`HYPOTHESIS`、`WHY_THIS_EXPERIMENT`、`PRECONDITIONS`、`SHARED_STATE_BEFORE`、`PROCEDURE`、`RAW_EVIDENCE`、`RESULT`、`ALTERNATIVE_EXPLANATIONS`、`ATTRIBUTION_CONFIDENCE`、`PROTOCOL_VIOLATION`、`SHARED_STATE_AFTER`、`NEW_UNKNOWNS`、`NEXT_EXPERIMENT_CANDIDATE`。`RESULT` 只能是 `PASS / FAIL / INCONCLUSIVE`；Evidence strength 不得自动升级。Protocol violation 不删除独立 Evidence，但必须降低并显式记录 experiment compliance。

Batch Final Output 必须综合回答：`WHAT_WE_DID_NOT_KNOW_BEFORE`、`FACTS_PROVEN`、`FACTS_DISPROVEN`、`FACTS_INCONCLUSIVE`、`NEW_MECHANISMS_DISCOVERED`、`ALTERNATIVE_EXPLANATIONS`、`EVIDENCE_ATTRIBUTION_STATUS`、`ENVIRONMENT_CONTAMINATION_STATUS`、`PROTOCOL_VIOLATIONS`、`PRODUCT_CONSTRAINTS_DISCOVERED`、`NEXT_HIGHEST_VALUE_EXPERIMENT_BATCH`；不得只罗列实验。

Autonomy hierarchy 是 hard invariant：`Sub-Agent autonomy < Experiment Coordinator Batch Contract < Browser Lead hard budgets / forbidden actions / stop conditions`。内部自主权可以调整 task decomposition、Sub-Agent allocation、hypothesis ordering 和 next-experiment selection；不得改变 hard budget、forbidden actions、Evidence requirements、安全边界或 Browser-defined stop conditions。

明确 Out of scope：generic multi-agent scheduler、universal orchestration framework、unlimited autonomous research、共享 Runtime 的同时 mutation、替代 Browser supervision、Transport redesign、Hook redesign，以及在当前 Work Item 内实现完整 Experiment Batch framework。

## Files to read

- `AGENTS.md`
- `README.md`
- `docs/index.md`
- `docs/adr/0003-agent-collaboration-framework.md`
- `docs/specs/agent-collaboration-protocol.md`
- `docs/specs/opencli-session-discovery.md`
- `docs/specs/research-review-loop.md`
- `docs/specs/antigravity-completion-gate-adapter.md`
- `docs/adr/0004-antigravity-completion-gate-adapter.md`
- `skills/research-review-lead/SKILL.md`
- `runtime/completion_gate.py`
- `adapters/antigravity/stop_hook.py`

## Validation

- **Command:** `$env:PYTHONDONTWRITEBYTECODE='1'; python scripts/test_opencli_transport.py`
- **Result:** Passed；169/169。受限沙箱不能创建 Windows temp fixtures，随后在获批环境运行完整 suite；只测试当前旧实现基线，不表示 R2 `send` Product alignment 或 `AC8` 已完成。
- **Command:** `$env:PYTHONDONTWRITEBYTECODE='1'; python scripts/check_skill_package.py`
- **Result:** Checker 内置的 120 秒 Transport runner 在本机超时；底层同一 169-test suite 以 139.8 秒独立完成并全部 PASS。未为 Handoff 扩大范围修改 checker timeout。
- **Command:** `python scripts/check_docs.py`
- **Result:** Passed（exit 0）；19 Markdown files registered；AGENTS.md 78/100；无禁用路径、垃圾副本或 `.DS_Store`。
- **Command:** `git diff --check`
- **Result:** Passed（exit 0；只有工作树 LF→CRLF 提示，无 whitespace error）。
- **Artifact hygiene:** 未创建日期 Handoff 文档，未修改 Transport、Hook 或 Adapter，未运行 Browser/Lab；仓库根无 `__pycache__` 或测试 temp artifact。
- **Last verified:** 2026-08-11

