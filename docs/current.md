# Current Project State

## Project identity

- **Name:** Agent Project System
- **Repository root:** `E:\PROJECTS\agent-project-system`
- **Remote:** `https://github.com/carllx/agent-project-system.git`
- **Branch:** `main`

## Active Work Item

- **ID:** `MULTILINE-PACKET-DELIVERY-001`
- **Name:** 确认并修复完整 Packet 进入 Browser 的传输边界
- **Review decision:** `PASS_WITH_DEBT`
- **Work Item state:** `ACHIEVED`
- **Skill status:** `PACKET_DELIVERY_READY`
- **Baseline commit:** `c867a7daf149d4d2f99a7bc55d15950f1da85a9b`
- **Current objective:** 已完成。Windows `opencli.cmd` 的多行 argv 边界已由单行紧凑 JSON Packet 修复并通过真实 Browser 完整送达验证。

## Acceptance criteria

- 先修复 `test_manual_recover_preserves_original_send_started_at` 的秒级时钟脆弱断言；保持 Transport 产品代码与语义不变，并通过全部本地测试。
- 固定三行 Packet 在输入、Wrapper、子进程前和实际 argv/stdin 各层的长度、行数、SHA-256 与 Marker 状态必须可核对。
- 纯本地证明 Python 直传、Windows `.cmd` 转发和当前 `run_opencli` 调用方式是否保留多行；不得先调用 ChatGPT。
- 只根据本机 OpenCLI 1.8.6 `ask` / `send` help 选择一个最小候选，并用唯一 `PACKET-INTEGRITY-001-R1` 真实发送一次。
- 只有真实 Browser user turn 完整显示三行与结束 Marker 后，候选方式才可进入 Wrapper；不得重发同 Message ID，不 commit 或 push。

## Completed

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

- 正式 Browser RR Review 两轮循环尚未验收。
- ADR 等待 `FIRST-USE-LOOP-001` 通过后创建。

## Decisions pending

- None.

## Next action

- 创建当前五文件本地 Commit；提交验证干净后，以该 Commit 为基线立即开始 `FIRST-USE-LOOP-001`。

## Files to read

- `AGENTS.md`
- `README.md`
- `docs/index.md`
- `scripts/check_skill_package.py`
- `scripts/test_check_skill_package.py`

## Last validation

- **Command:** `python -m unittest -v scripts.test_check_skill_package`
- **Result:** Passed 14/14；成功输出版本断言动态读取权威 `VERSION` 文件并保持其余输出逐字断言。
- **Command:** `python scripts/test_opencli_transport.py`
- **Result:** Passed all 123 directly invoked pure-local Transport tests；AST discovered 123，direct listed 123，Missing 0，Duplicate 0，Failed 0，Skipped 0。
- **Command:** `python scripts/check_skill_package.py`
- **Result:** Passed；受控 Runner 发现并逐项执行全部 123 项 Transport 测试，Missing 0，Duplicate 0，Failed 0，Skipped 0。
- **Command:** `python scripts/check_docs.py`
- **Result:** Passed; 14 registered Markdown files.
- **Command:** `python skills/research-review-lead/scripts/opencli_transport.py --help`
- **Result:** Passed; direct script execution remains available.
- **Command:** multi-error fixture, Runner invocation probe and temporary AST complexity probe.
- **Result:** Baseline and current normalized stdout/stderr hashes match; Runner called once; `main()` is 19 lines with estimated complexity 3 and nesting 2.
- **Command:** `git diff --check`
- **Result:** Passed.
- **Scope:** 真实 OpenCLI/Browser 仅用于唯一 `PACKET-INTEGRITY-001-R1` 完整性探针；发送一次、创建一个 Conversation、未重发、未 commit 或 push。除该探针外没有发送消息。
- **Last verified:** 2026-08-06
