# Current Project State

## Project identity

- **Name:** Agent Project System
- **North star:** 建立一套与具体 IDE 和 Transport 解耦的 **Agent Collaboration Framework**，使 Browser Lead 与 IDE Agent 能通过可定义、可观察、可恢复、可审查、可测试的协议形成长期工作闭环。见 `docs/adr/0003-agent-collaboration-framework.md`。
- **Repository root:** `E:\PROJECTS\agent-project-system`
- **Remote:** `https://github.com/carllx/agent-project-system.git`
- **Branch:** `main`
- **HEAD / reviewed product baseline:** `7a7536701bab5855713f00dfc85a6d90e648a229`（`docs: close Antigravity completion gate work item`）
- **Source Skill VERSION:** `0.4.15`。
- **OBSERVED_LOCAL_INSTALL_PATH:** `C:\Users\carll\.codex\skills\research-review-lead`；目录存在，VERSION `0.4.15`，九个文件与源包逐文件 SHA-256 一致。
- **HISTORICAL_DESIGN_TARGET:** `$HOME/.agents/skills/research-review-lead`（ADR-0002）；本机当前不存在。
- **CANONICAL_DEPLOYMENT_PATH:** `UNVERIFIED`。仓库没有安装脚本；项目历史记录了 `.codex\skills` 的本机安装结果，但不能证明它是所有平台通用的 canonical Codex 用户级 Skill 路径。

## 系统目标

Agent Project System 不是单独的 RR Lead Skill，也不是 OpenCLI Transport，而是一套与具体 IDE 和 Transport 解耦的 Agent Collaboration Framework：

```text
Agent Project System
→ Agent Collaboration Framework
→ Browser Lead / IDE Agent Collaboration Protocol
→ Runtime / Orchestration
→ Transport / IDE Adapters
```

- **Browser Lead：** 负责规划、架构、Review 与被授权范围内的技术判断。
- **用户：** 保留目标、范围、权限、风险、成本和重要产品方向的最终决定权。
- **参考 IDE 顺序：** Antigravity 为第一参考 IDE；Codex 后续用于跨 IDE 通用性验证。
- **OpenCLI：** 只是 Transport Adapter，不等于整个系统。
- **rr-lead-skill-lab：** 独立实验环境，不是正式产品源码仓库。

## 当前模块

- `skills/research-review-lead/`：已登记的正式运行模块（RR Lead Loop + 确定性 bootstrap + manual-export fallback），VERSION `0.4.15`。
- OpenCLI Transport Adapter：`skills/research-review-lead/scripts/opencli_transport.py` 中的 Transport 层实现，仅作为框架的适配器。
- `runtime/completion_gate.py`：IDE-independent Completion-Gate Policy；`adapters/antigravity/stop_hook.py`：Antigravity Stop lifecycle translation。两者已通过 `ACF-AG-ADAPTER-001` Browser Final Review，尚未部署。

## Active Work Item

- **ID:** `OPENCLI-SESSION-DISCOVERY-001`
- **Name:** OpenCLI Session Discovery and Identity Contract
- **State:** `IN_PROGRESS`
- **Workflow state:** `EXECUTING`
- **Review Request ID:** `OPENCLI-SESSION-DISCOVERY-001-R1-INTERMEDIATE`
- **Product baseline:** `7a7536701bab5855713f00dfc85a6d90e648a229`。
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

### Current assessment

- **Known:** `/new` 不是 exact Conversation；OpenCLI 1.8.6 `new` 只观察到 Status；status URL、ask identity、history candidate 与 actual delivery 不能混用；`EMPTY_RESULT` 只证明空页；timeout 为 `DELIVERY_UNKNOWN`；同一 Message ID 只允许一次写入；exact marker 错投到 pre-send Conversation 为 `MISROUTED_DELIVERY`。
- **Unknown:** 新建后发送前取得稳定 exact ID 的机制；可靠 explicit-target write 的实际行为；第一条消息生成 ID 时如何原子证明 target intent 与 delivery；timeout/navigation error 下 ask identity、status 与 detail 的稳定关系。
- **Lab:** `OPENCLI-SESSION-IDENTITY-MIN-001` handoff 已定义，等待 Browser Lead 审查后交给 Lab；本轮未运行 Browser/OpenCLI 实验。
- **Product implementation:** 未开始；必须等待必要机制 Evidence，不以现有 Wrapper 行为冒充 Contract 已满足。

### Intermediate Browser Review

- **R1:** `APPROVE`；`PROTOCOL_VERSION=ACF-0.1`，`IN_REPLY_TO_REVIEW_REQUEST_ID=OPENCLI-SESSION-DISCOVERY-001-R1-INTERMEDIATE`，`REVIEW_KIND=INTERMEDIATE`。
- **MET:** `AC1`、`AC2`、`AC5`、`AC6`、`AC7`、`AC9`、`AC10`。
- **UNVERIFIED:** `AC3`、`AC4`，等待 `OPENCLI-SESSION-IDENTITY-MIN-001` Lab Evidence。
- **NOT_MET:** `AC8`，Product implementation/tests 尚未开始且不得在 Lab Evidence 前开始。
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

### Review artifact access path

- GitHub 可用且 Browser 有权访问时，Review Request 优先携带 repository、Review Branch、Commit SHA 与适用的 baseline SHA，Browser 直接审查真实代码和 Diff。
- GitHub 只是 Review Artifact access path，不是 Completion Authority、ACF Protocol 或实时 Transport；无 GitHub 时继续使用 Evidence Packet / Manual Relay。
- 通用规则记录在 `docs/specs/agent-collaboration-protocol.md`；RR-specific 映射记录在 `docs/specs/research-review-loop.md`。

## Latest Completed Work Item

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
- 当前没有 Active Product Work Item。

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
- `DECISION_CANDIDATE: ANTIGRAVITY_HOOK_DEPLOYMENT`：另行裁决 Global Hook 与 workspace-local Hook 的产品部署形式。
- 两项均为 `NOT_STARTED`，不阻塞 `OPENCLI-SESSION-DISCOVERY-001`，也未被启动为并行 Active Work Item。

## Files to read

- `AGENTS.md`
- `README.md`
- `docs/index.md`
- `docs/adr/0003-agent-collaboration-framework.md`
- `docs/specs/agent-collaboration-protocol.md`
- `docs/specs/opencli-session-discovery.md`
- `docs/specs/antigravity-completion-gate-adapter.md`
- `docs/adr/0004-antigravity-completion-gate-adapter.md`
- `runtime/completion_gate.py`
- `adapters/antigravity/stop_hook.py`

## Previous validation baseline

- **Command:** `$env:PYTHONDONTWRITEBYTECODE='1'; python -m unittest -v scripts.test_antigravity_completion_gate`
- **Result:** Passed；10/10（含 pending agreed Acceptance Criteria 的缺失、完整、重复/malformed coverage 回归，以及 Policy、权威 Final Approval、stale/mismatched Approval、等待状态、bounded continuation、精确 route/Work Item 绑定与真实 CLI translation）。受限沙箱不能正确创建 Python 临时目录，因此相同测试在获批的沙箱外进程中运行；未执行真实 Hook 或 Browser 实验。
- **Command:** `python scripts/check_docs.py`
- **Result:** Passed（exit 0）；18 Markdown files registered；AGENTS.md 78/100；无禁用路径、垃圾副本或 `.DS_Store`。
- **Command:** `git diff --check`
- **Result:** Passed（exit 0；只有工作树 LF→CRLF 提示，无 whitespace error）。
- **Command:** `git status --short` / `git diff --stat`
- **Result:** 合并后收口变更仅为 `docs/current.md`、`docs/index.md` 与 `docs/adr/0004-antigravity-completion-gate-adapter.md`；未暂存。stat 为 3 files changed、16 insertions、14 deletions。
- **Artifact hygiene:** 仓库根无测试 `tmp*` 目录，无 `__pycache__`；产品代码与测试中无 Lab 路径、实验 ID、Lab Conversation ID、`gate_state.json` 或 `HAS_CONTINUED_THIS_REVISION` 硬编码。
- **Last verified:** 2026-08-09
