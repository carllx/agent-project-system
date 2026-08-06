# Current Project State

## Project identity

- **Name:** Agent Project System
- **Repository root:** `E:\PROJECTS\agent-project-system`
- **Remote:** `https://github.com/carllx/agent-project-system.git`
- **Branch:** `main`

## Active Work Item

- **ID:** `OPENCLI-ASK-TIMEOUT-001`
- **Name:** 恢复有界 ask 与两阶段发送/回复恢复
- **Review decision:** `PASS_WITH_DEBT`
- **Work Item state:** `ACHIEVED`
- **Skill status:** `BLOCKED_FIRST_USE`
- **Baseline commit:** `ea7f01efc3da305804df957a21f879ca45d85883`
- **Current objective:** 使 OpenCLI ask 在 Wrapper 的短硬超时内结束整个本地进程树，保留同 Message ID 禁止重发语义和后续只读恢复预算。

## Acceptance criteria

- OpenCLI 自身 timeout 不可靠时，Wrapper 仍在全局实验预算前硬终止 ask 本地进程树。
- ask 超时保留 `message_send_count=1` 和同 Message ID 禁止重发，不得回退为 `NOT_SENT`。
- ask 超时后持久化 state 并保留一次只读 `recover` 预算；`recover` 不得调用 ask、send 或 new。
- 只读恢复可绑定 Conversation，在回复未完成时保留 ID，并能接受稍后出现的同源身份绑定 RR Review。
- 不修改 Response Identity、Decision、发送次数、Recovery/Detail 预算上限或其他非阻断范围；不重发旧 Message ID，不 commit 或 push。

## Completed

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

- 首次真实循环仍受消息可观测性阻断：OpenCLI ChatGPT detail 没有暴露完整消息正文，无法读取完整 `MESSAGE_ID`、RR Review Envelope 和 `NEXT_WORK_ORDER`。

## Debt

- OpenCLI ChatGPT detail 没有暴露完整消息正文；这是当前外部可观测性 Debt，不否定 ask timeout 与 recovery identity 修复已经通过。
- 高复杂度协议函数只是被隔离，尚未简化。
- `opencli_transport.py` 仍约 1325 行。
- `send_command` 等状态机热点尚未处理。

## Decisions pending

- None.

## Next action

- 创建独立阻断 Work Item，只读调查现有 MVP-002 / MVP-003 Conversation 的完整消息可观测性；不得发送新消息或创建新 Conversation。

## Files to read

- `AGENTS.md`
- `README.md`
- `docs/index.md`
- `scripts/check_skill_package.py`
- `scripts/test_check_skill_package.py`

## Last validation

- **Command:** `python -m unittest -v scripts.test_check_skill_package`
- **Result:** Passed all 14 standard unittest cases, including success/failure output, multi-error order, one Runner invocation and Runner failure propagation.
- **Command:** `python scripts/test_opencli_transport.py`
- **Result:** Passed all 119 directly invoked pure-local Transport tests.
- **Command:** `python scripts/check_skill_package.py`
- **Result:** Passed; controlled Runner called all 119 discovered tests exactly once, package version `0.4.12`.
- **Command:** `python scripts/check_docs.py`
- **Result:** Passed; 14 registered Markdown files.
- **Command:** `python skills/research-review-lead/scripts/opencli_transport.py --help`
- **Result:** Passed; direct script execution remains available.
- **Command:** multi-error fixture, Runner invocation probe and temporary AST complexity probe.
- **Result:** Baseline and current normalized stdout/stderr hashes match; Runner called once; `main()` is 19 lines with estimated complexity 3 and nesting 2.
- **Command:** `git diff --check`
- **Result:** Passed.
- **Scope:** 本地验证未调用真实 OpenCLI 或 Browser、未发送消息；后续只读恢复证明 detail 消息正文不完整。
- **Last verified:** 2026-08-06
