# Current Project State

## Project identity

- **Name:** Agent Project System
- **Repository root:** `E:\PROJECTS\agent-project-system`
- **Remote:** `https://github.com/carllx/agent-project-system.git`
- **Branch:** `main`

## Active Work Item

- **ID:** `BOOTSTRAP-MANUAL-RELAY-001`
- **Name:** 确定性 Browser Bootstrap 与 Manual Relay fallback
- **Review decision:** `NONE`（本地完成；待重新安装后的真实 Browser 验收）
- **Work Item state:** `IN_PROGRESS`
- **Skill status:** `INSTALL_PENDING`
- **Baseline commit:** `2f01246`
- **Skill version before:** `0.4.14`
- **Skill version after:** `0.4.15`
- **Current objective:** 补齐 `bootstrap`（确定性单次 init+context 发送）与 `manual-export`/`MANUAL_RELAY_REQUIRED`（自动恢复预算耗尽时人工中转），本地全绿后提交、重新安装，并在真实 Browser 上完成 Gate 1–5 验收。

## Corrected acceptance status

- `SOURCE_PACKAGE_TESTED=true`
- `PACKAGE_COPIED_TO_CANDIDATE_PATH=false`（重新安装进行中）
- `DISCOVERY=UNVERIFIED`（待全新会话运行时观察；不以 frontmatter 推断为 PASS）
- `LIVE_TRANSPORT_DELIVERY_VERIFIED=true`
- `RR_LEAD_PROTOCOL_VERIFIED=false`（待 Gate 4 新版本 Live ACK）
- `DETERMINISTIC_BOOTSTRAP_IMPLEMENTED=true`（本地测试全绿；真实 Browser 未验）
- `MANUAL_RELAY_IMPLEMENTED=true`（本地测试全绿）
- `TWO_ROUND_SMOKE_VERIFIED=false`
- `LIVE_SMOKE_TEST_PASSED=false`

## Acceptance criteria

- `bootstrap` 由 Wrapper 读取 init+context 文件，去除 UTF-8 BOM、统一换行、发送前拒绝非法 UTF-8/孤立 surrogate，按固定顺序与唯一边界组装，manifest 含字节数/字符数/行数/SHA-256，复用现有 send+bounded recover，同一 Message ID 只发一次。
- `manual-export` 不调用 OpenCLI、不建 Conversation、不增 send count；输出 `TRANSPORT_STATE: MANUAL_RELAY_REQUIRED`、`WORK_ITEM_STATE: IN_PROGRESS`、`send_attempted=false`，导出 hash 与准备发送正文一致。
- 自动 Transport 恢复预算耗尽后进入 `MANUAL_RELAY_REQUIRED`，不得把 Work Item 标记为永久失败。
- 新增 18 项纯本地回归全部通过；至少一个新测试在旧版本（0.4.14）上失败，在新版本（0.4.15）通过。
- 本地验收、提交、重新安装与 Gate 1–5（Discovery/Bootstrap/ManualRelay/LiveACK/Smoke）全部通过后，才可声明 `LIVE_SMOKE_TEST_PASSED`。

## Completed

- `BOOTSTRAP-MANUAL-RELAY-001` adds `opencli_transport.py bootstrap`（确定性拼装 init+context 的单次发送）与 `manual-export`（`MANUAL_RELAY_REQUIRED` 人工中转），以及自动恢复预算耗尽进入 `MANUAL_RELAY_REQUIRED`/`IN_PROGRESS` 的 fallback。VERSION 由 `0.4.14` 升至 `0.4.15`。
- `bootstrap` 由 Wrapper 读取两个文件：去除 UTF-8 BOM、CRLF/LF 统一、发送前拒绝非法 UTF-8 与孤立 surrogate；按固定顺序组装 `BEGIN_RR_LEAD_INITIALIZATION`/`END_RR_LEAD_INITIALIZATION` 与 `BEGIN_CONTEXT_PACKET`/`END_CONTEXT_PACKET`；manifest 含 byte/char/line/SHA-256；复用现有 `send_command` 与 bounded recover，不新建第二套 Transport。
- `manual-export` 不调用 OpenCLI、不建 Conversation、不增 send count；输出完整可复制包（Work Item/Message/Round/Type、字节数/行数/SHA-256、`BEGIN_MESSAGE`/`END_MESSAGE`、原文），state 置 `TRANSPORT_STATE: MANUAL_RELAY_REQUIRED`、`WORK_ITEM_STATE: IN_PROGRESS`、`send_attempted=false`，hash 与准备发送正文一致。
- 新增 18 项相关纯本地回归；AST 发现、direct 列表、direct 执行与受控执行均为 169，Missing/Duplicate/Failed/Skipped 均 0。已用 `git stash` 证明 `test_bootstrap_same_inputs_produce_stable_hash`、`test_manual_export_packet_hash_matches_body`、`test_automatic_recovery_exhaustion_enters_manual_relay_required` 在旧版本（无 bootstrap/manual-export）上失败，在新版本通过。
- 本地验收全部通过：`check_skill_package.py`（0.4.15，受控执行 169 项）、checker unittest 14/14、`check_docs.py`（14 个登记 Markdown）、`bootstrap --help` 与 `manual-export --help`、`git diff --check`。

以下为先前 `RESPONSE-PENDING-RESUME-001` 的历史记录，保留作事实来源。

- `RESPONSE-PENDING-RESUME-001` implements `recover --continue-pending` with a fresh per-invocation operation budget, a saved-Conversation-only detail and necessary same-source status/read fallback, and no ask/send/new path.
- Runtime now persists `pending_response_continuation_count`, `pending_response_last_checked_at`, and `pending_response_last_result`; the default maximum is three explicit continuations, after which an incomplete response becomes `BLOCKED_RESPONSE_TIMEOUT` without deleting send evidence.
- Stable wrong or incomplete RR identity becomes `RESPONSE_IDENTITY_REJECTED`; the parser's underlying reason is retained as `pending_response_last_identity_status`. Exact RR envelope and identity requirements are unchanged.
- Added ten focused pending-response regressions without reorganizing the Transport test file. AST discovered, direct listed, direct executed, and controlled executed are all 133; Missing 0, Duplicate 0, Failed 0, Skipped 0. Checker unittest remains 14/14.
- Skill version is `0.4.14`; source and Lab contain the same nine relative files with identical SHA-256 values.
- Initial read of Conversation `6a7461e1-b498-83ea-99b4-014b43d2f0a2` found one stable Assistant response. Status before and after both identified the same Conversation, and no read fallback was needed for that initial observation.
- The real formal continuation used the original state once, did not alter `message_send_count=1`, and invoked no ask/send/new. It rejected the response because it contains `REPLY_TO_MESSAGE_ID` rather than the required `IN_REPLY_TO_MESSAGE_ID`.
- Added strict compatibility for the single observed `REPLY_TO_MESSAGE_ID` alias. Exact alias values normalize to the sole authoritative `IN_REPLY_TO_MESSAGE_ID`; wrong, empty, duplicate, missing, or conflicting reply identities are rejected. Browser initialization remains canonical and Skill version remains `0.4.14`.
- Added eight focused alias regressions. AST discovered, direct listed, direct executed, and controlled executed are all 141; Missing 0, Duplicate 0, Failed 0, Skipped 0. Source and Lab again contain the same nine relative files with identical SHA-256 values.
- Offline reparse of the saved stable Round 1 response confirmed `REPLY_ID_SOURCE: LEGACY_ALIAS` and normalized the exact expected Message ID, but exposed protocol-external top-level `MESSAGE_ID` and `MESSAGE_TYPE` lines. Under the unchanged parser these lines become part of `WORK_ITEM_ID` and `ROUND`, so the formal result is `RESPONSE_IDENTITY_MISMATCH`. No Round 2 message was sent.
- Parser now treats every unindented strict uppercase field header as a boundary before applying a whitelist. Unknown top-level fields return `RESPONSE_PROTOCOL_REJECTED`; optional `MESSAGE_ID` and `MESSAGE_TYPE` metadata are accepted only when they exactly identify `<WORK_ITEM_ID>-R<ROUND>-REVIEW` and `RR_REVIEW`.
- Added ten focused field-boundary and optional-metadata regressions. AST discovered, direct listed, direct executed, and controlled executed are all 151; Missing 0, Duplicate 0, Failed 0, Skipped 0.
- Reparse of the saved Round 1 response now verifies `WORK_ITEM_ID: FIRST-USE-LOOP-001`, `ROUND: 1`, response Message ID `FIRST-USE-LOOP-001-R1-REVIEW`, response type `RR_REVIEW`, legacy reply source, and exact normalized outbound Message ID.
- `FIRST-USE-LOOP-001` Round 2 sent `FIRST-USE-LOOP-001-R2-EVIDENCE` exactly once to the same verified Conversation `6a7461e1-b498-83ea-99b4-014b43d2f0a2`. The compact outer payload was one physical line; the fresh marker body was exactly 147 UTF-8 bytes, three lines, SHA-256 `738d60d4f37313b27fcc439d20411b759ef14139bea94acda805c0f66cdb2e05`.
- The ask timed out after the single send. One bounded manual recovery confirmed delivery and one explicit pending continuation obtained a verified final review without ask/send/new. The final Browser review returned `PASS`, `WORK_ITEM_STATE: ACHIEVED`, canonical reply identity, response Message ID `FIRST-USE-LOOP-001-R2-REVIEW`, response type `RR_REVIEW`, and no blockers.
- `FIRST-USE-LOOP-001` is `ACHIEVED`; `FIRST_USABLE_VERSION: 0.4.14`; `FURTHER_REFACTOR_REQUIRED_BEFORE_USE: false`. No user message copying, manual Browser intervention, same-ID resend, Round 3, or push occurred.
- `FIRST-USE-LOOP-001` Lab deployment verified all nine source-relative files with identical SHA-256 values; Lab Wrapper `--help` exited 0.
- Round 1 used `FIRST-USE-LOOP-001-R1-EVIDENCE` exactly once through `send --prepare-new`; no same-ID resend and no user message copying occurred.
- Round 1 created and verified Conversation `6a7461e1-b498-83ea-99b4-014b43d2f0a2`. The persisted payload was one physical line, 4171 bytes, SHA-256 `d4816259105593e3a78d9044365a52fc5d80d52533454b3cd73c4eab9debfdee`, with Work Item, Message ID, and end-sentinel markers present.
- The bounded recovery detail contains one stable User message of 4181 characters with exact Work Item ID, exact Message ID, end sentinel, source commit, local packet test evidence, and real Browser probe evidence; Round 1 Packet delivery is complete.
- The only ask timed out and was hard-terminated. One manual bounded recovery used status, history, and one detail without ask/send/new; it established the verified target but found no Assistant message, leaving `RESPONSE_PENDING`.
- `PACKET_DELIVERY_READY: true`；`MESSAGE_OBSERVABILITY_READY: true`；Skill 版本为 `0.4.13`。
- `ROOT_CAUSE`: Windows `opencli.cmd` 无法完整转发包含换行的 argv。
- `SELECTED_METHOD`: 使用单行紧凑 JSON Packet；原始多行正文在 `EVIDENCE` 字段中无损 round-trip，身份和结束 Sentinel 保留在顶层。
- `DELIVERY_EVIDENCE`: Browser 用户消息包含固定三行测试内容、`END_SENTINEL` 和精确 `MESSAGE_ID`。
- `SECURITY_AND_PRIVACY`: Runtime 状态与日志只保存长度、SHA-256、Marker 状态和 `argv` 方式，不保存 Packet 正文。
- Package Checker 标准 unittest 通过 14/14；Transport AST 发现、direct 列表、direct 执行和受控执行均为 123，Missing 0、Duplicate 0、Failed 0、Skipped 0。
- `test_manual_recover_preserves_original_send_started_at` 的偶发失败根因为 `utc_now()` 使用秒精度，发送与 manual recover 可以产生相同时间字符串；测试已改为验证 original send 时间不变且 manual recover 使用 `current_operation_started_at`，产品代码未为此改变。
- 固定三行 Packet 在输入与 Wrapper 接收层均为 115 字节、115 字符、3 行、SHA-256 `db81e23a7a5b8b9ce668567eaa00288ef35f318b1ea9a44d38d410a01d3aee3b`；加入 Transport 身份头后的调用前 Prompt 为 226 字节、226 字符、8 行，三个 Marker 仍全部存在。
- Python 直接传递多行 argv 保留 115 字节和同一 SHA-256；Windows `.cmd` 转发只把第一行的 27 字节交给接收器，当前 `run_opencli -> opencli.cmd` 同样在 OpenCLI 前丢失后续行，根因为 `.cmd` 多行 argv 转发边界。
- 本机 OpenCLI 1.8.6 `ask` / `send` 都只接受位置参数 `prompt`，没有 stdin、prompt-file、JSON-input 或 raw-text 选项；单行紧凑 JSON 经当前 `.cmd` 调用保持 677 字节与 SHA-256 不变。
- 唯一真实探针 `PACKET-INTEGRITY-001-R1` 只发送一次；Conversation `6a745b6c-51e4-83ea-affa-9a440036eee6` 的显式 detail/read 与只读 DOM 都显示完整三个 Marker 和结束 Sentinel，Assistant ACK 也精确确认 `END_SENTINEL_SEEN: true`、`LINES_RECEIVED: 3`。
- Wrapper 已改为把完整 Packet 正文无损封装进单行紧凑 JSON 的 `EVIDENCE` 字段，保留顶层身份与必需路由字段；状态只记录长度、SHA-256、Marker 状态和 `argv` 方式，不新增 Packet 正文日志。Skill 版本由 `0.4.12` 升至 `0.4.13`。
- 新增四项纯本地回归；直接 Transport 123/123 全部通过，未重发探针 Message ID，Browser 只读 session 已关闭。
- `OPENCLI-MESSAGE-OBSERVABILITY-001` 已按 `REVISE / STALLED` 停止：detail、read 与 Browser DOM 都只显示相同的 31 字符 Work Item ID，但这不能区分“完整正文不可观察”和“完整 Packet 从未送达”。
- 当前正确结论为 `FULL_MESSAGE_OBSERVABILITY: UNVERIFIED`、`FULL_PACKET_DELIVERY: UNVERIFIED`、`VISIBLE_BROWSER_MESSAGE: WORK_ITEM_ID_ONLY`；不得把 OpenCLI 1.8.6 完整消息可观测性写成已证明不支持。
- `OPENCLI-MESSAGE-OBSERVABILITY-001` 离线审计确认 MVP-002 / MVP-003 detail raw 只有 `Role` / `Text` / `Generating` / `StableSeconds`，每条 Text 只含 31 字符的 Work Item ID，不含完整 Message ID、RR Review Envelope 或 `NEXT_WORK_ORDER`。
- 本机 OpenCLI 1.8.6 `getVisibleMessages()` 从可见 DOM 的 `innerText/textContent` 提取消息，detail formatter 只映射字段，两处都没有长度截断逻辑；raw 中也不存在隐藏的 full-text 字段。
- Primary 与 Secondary 都有 MVP-003 baseline/history/status raw provenance；Primary 由发送后 status 首次观测，Secondary 由发送后 history 首次观测，两者都不在发送前 baseline。
- Primary 和 Secondary 的 `detail -> status -> read -> status` 都证明了读取前后 Conversation URL 同源；Primary 仍只有 Work Item ID，Secondary 被证明为非目标 Candidate。
- 受限 `opencli browser` 只读观察已仅打开 Primary；DOM state 和精确 user/assistant turn 文本同样只有 Work Item ID，随后已关闭命名 session，未点击、输入或发送。
- Wrapper 在 OpenCLI ask 不遵守自身 timeout 时硬终止完整本地进程树，同时保留 `message_send_count=1`、`DELIVERY_UNKNOWN` 和同 Message ID 禁止重发语义。
- 自动 Recovery 与 manual recover 使用独立的一次性预算；manual recover 使用新的操作时间预算，不调用 ask、send 或 new，也不改变发送次数。
- Candidate Conversation ID 单调保存；空 status 不覆盖 Candidate，冲突 Candidate 被显式记录，只有精确消息证据才能晋升为 verified target。
- Checker 标准 unittest 14/14 与 Transport 119/119 全部通过，共 133/133 项独立测试；受控 Runner 发现并逐项执行全部 119 项 Transport 测试。
- `check_skill_package.py::main` 从 292 行、项目内部 AST 近似复杂度 47 降至 19 行、复杂度 3。
- 成功输出、失败退出码、31 条错误文本及其顺序与重构前保持一致。
- Transport Runner 仍在相同检查阶段执行，并且每次正常包检查只执行一次。
- Checker 标准 unittest 14/14、直接及受控 Transport 测试 101/101 全部通过。
- `COMPLEXITY-DELTA-002` 已由 Browser RR Lead 判定 `PASS` / `ACHIEVED`；基线 Commit 为 `f49c3e2b43d5f78c0b6a5c005d8cabd44313ba99`，复测未修改仓库文件。
- `COMPLEXITY-BASELINE-001` 已由 Browser RR Lead 判定 `PASS` / `ACHIEVED`；基线 Commit 为 `fb99621a58dbec60cd1354960f8e6675dfe3f507`，调查未修改仓库文件。
- 将三个实验协议验证函数及八个专用协议常量抽取到 `scripts/experiment_protocol.py`；Transport 通过基于 `__file__` 的本地加载兼容性重导出原 API。
- 抽取前后函数 AST dump 全部匹配；三个函数均只有一个定义，协议常量均只有一个字面权威定义。
- 新增独立模块加载、Transport API 重导出、直接 `--help` 三项纯本地回归；Transport 套件由 98 项增至 101 项。

- 修改前调查确认 Wrapper 没有正式 RR Review Parser；`ask_response()` 只提取文本，`inspect_messages()` 只判断目标用户消息后是否存在稳定 Assistant 文本。
- 当前基线 Worktree clean，Skill 版本为 `0.4.8`，Transport 纯本地测试为 75 项。
- 新增来源、role、消息顺序和三项内容身份的结构化验证；只有唯一完整匹配回复才写入 `verified_rr_review` 并使 `official_response_eligible=true`。
- 新增 12 项纯本地回复身份测试；完整 Transport 套件从 75 项增至 87 项并全部通过，受控检查器也直接调用全部 87 项。
- Skill 与 RR Lead 初始化规则要求精确回显 `WORK_ITEM_ID`、`IN_REPLY_TO_MESSAGE_ID` 和 `ROUND`；版本按 patch 规则升至 `0.4.9`。
- 修复来源校验自我满足：不可变 `ResponseMessageBatch` 绑定同一次 detail/ask 的 Conversation ID 与消息，调用层先建立 verified target，`accept_delivery` 不再写入或覆盖 target。
- 重复 outbound 精确锚点在正式 Parser 前返回 `OUTBOUND_MESSAGE_IDENTITY_AMBIGUOUS`；正式 Assistant 回复只从完整 `RR_REVIEW_BEGIN` / `RR_REVIEW_END` 封包解析。
- 新增 11 项纯本地回归，Transport 套件从 87 项增至 98 项并全部通过；受控检查器直接调用全部 98 项，Skill 版本升至 `0.4.10`。
- 未调用真实 OpenCLI 或 Browser，未发送消息；未修改 Decision 协议或 `START_NEW_AND_SEND` 的发送、恢复和 Conversation 创建预算。

## Blockers

- None.

## Debt

- ADR 等待 `FIRST-USE-LOOP-001` 通过后创建。
- 后续 Evidence 应区分 `PROBE_CONVERSATION_ID` 与 `RR_LOOP_CONVERSATION_ID`，避免把独立探针 Conversation 误写为当前 Loop Conversation。

## Decisions pending

- None.

## Next action

- 已提交并被安装到 `C:\Users\carll\.codex\skills\research-review-lead`；本地 `bootstrap`/`manual-export` 桌面验证（Gate 2/3）通过。
- Gate 1（真实 Discovery）在本执行环境无法创建全新会话，状态为 `NEEDS_HUMAN_FRESH_SESSION`：请新建一个全新 Codex 会话，观察 `research-review-lead` 出现在 Skill 列表、description 正确、可被明确选择；不要用 frontmatter 合法代替运行时发现。
- Gate 4/5（新版本 Live ACK 与两轮 Smoke）须在全新会话 + 真实 Browser RR Lead 会话中进行：以全新 Work Item/Message ID 跑 `bootstrap --prepare-new` 创建并发送一次，`recover` 确认，接收含 `MESSAGE_TYPE: RR_REVIEW`、`WORK_ITEM_ID`、`IN_REPLY_TO_MESSAGE_ID` 的 envelope；不要复用 `ACCEPT-LIVE-001` 或 `6a74b7d0-...`。当前活动标签正是被禁用的历史 Conversation，故本轮不发送实况消息。
- 在 Gate 1/4/5 与 Final Auditor 全部 PASS 前，不声明 `LIVE_SMOKE_TEST_PASSED`；暂不执行真实 `carllx-skills` 三轮架构评审。

## Files to read

- `AGENTS.md`
- `README.md`
- `docs/index.md`
- `scripts/check_skill_package.py`
- `scripts/test_check_skill_package.py`

## Last validation

- **Command:** `python scripts/test_opencli_transport.py`
- **Result:** Passed all 169 pure-local Transport tests; Missing 0, Duplicate 0, Failed 0, Skipped 0.
- **Command:** `python scripts/check_skill_package.py`
- **Result:** Passed; Version 0.4.15; controlled runner executed 169 tests exactly once.
- **Command:** `python -m unittest -v scripts.test_check_skill_package`
- **Result:** Passed 14/14.
- **Command:** `python scripts/check_docs.py`
- **Result:** Passed; 14 registered Markdown files.
- **Command:** `python skills/research-review-lead/scripts/opencli_transport.py bootstrap --help`
- **Result:** Passed; exposes `--prepare-new --work-item-id --message-id --init-file --context-file --state-file`.
- **Command:** `python skills/research-review-lead/scripts/opencli_transport.py manual-export --help`
- **Result:** Passed; exposes `--work-item-id --message-id --round --message-type --message-file --state-file`.
- **Command:** `git diff --check`
- **Result:** Passed.
- **Fail-on-old proof:** with only the transport source stashed to 0.4.14, `test_bootstrap_same_inputs_produce_stable_hash`, `test_manual_export_packet_hash_matches_body`, and `test_automatic_recovery_exhaustion_enters_manual_relay_required` failed (AttributeError / FileNotFoundError / AssertionError); restored source passed.
- **Last verified:** 2026-08-07
- **Command:** `python -m unittest -v scripts.test_check_skill_package`
- **Result:** Passed 14/14；成功输出版本断言动态读取权威 `VERSION` 文件并保持其余输出逐字断言。
- **Command:** `python scripts/test_opencli_transport.py`
- **Result:** Passed all 151 directly invoked pure-local Transport tests；AST discovered 151，direct listed 151，Missing 0，Duplicate 0，Failed 0，Skipped 0。
- **Command:** `python scripts/check_skill_package.py`
- **Result:** Passed；受控 Runner 发现并逐项执行全部 151 项 Transport 测试，Missing 0，Duplicate 0，Failed 0，Skipped 0。
- **Command:** `python scripts/check_docs.py`
- **Result:** Passed; 14 registered Markdown files.
- **Command:** `python skills/research-review-lead/scripts/opencli_transport.py --help`
- **Result:** Passed; direct script execution remains available.
- **Command:** multi-error fixture, Runner invocation probe and temporary AST complexity probe.
- **Result:** Baseline and current normalized stdout/stderr hashes match; Runner called once; `main()` is 19 lines with estimated complexity 3 and nesting 2.
- **Command:** `git diff --check`
- **Result:** Passed.
- **Scope:** 真实 OpenCLI/Browser 用于已完成的唯一 `PACKET-INTEGRITY-001-R1` 探针及本次 `FIRST-USE-LOOP-001` Round 1 正式发送；每个 Message ID 均只发送一次，无重发、无用户复制、无 commit 或 push。
- **FIRST-USE Round 1:** One formal `send --prepare-new` call sent `FIRST-USE-LOOP-001-R1-EVIDENCE` once. One bounded manual recovery established the new verified Conversation and complete User Packet but returned `RESPONSE_PENDING`; Round 2 was not sent.
- **First-use completion:** Saved Round 1 and live Round 2 reviews both passed exact identity parsing. Round 2 used one send and one pending continuation in the same Conversation; final Browser decision is `PASS / ACHIEVED`.
- **Last verified:** 2026-08-06

## Installation Acceptance
- **Platform Forensics:** PASS（既有 0.4.14 九文件包核对一致）
- **Installation:** PENDING（待重新安装 0.4.15）
- **Discovery:** UNVERIFIED（待全新会话运行时观察）
- **Manual Invocation:** PENDING
- **Handoff:** PASS
- **Browser Loop:** PENDING（待 Gate 4/5）
- **Completion Index:** 未声明（须 Final Auditor 通过）

