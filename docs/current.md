# Current Project State

## Project identity

- **Name:** Agent Project System
- **Repository root:** `E:\PROJECTS\agent-project-system`
- **Remote:** `https://github.com/carllx/agent-project-system.git`
- **Branch:** `main`

## Active Work Item

- **ID:** `EXTRACT-EXPERIMENT-PROTOCOL-001`
- **Name:** 抽取实验协议验证模块
- **Review decision:** `PASS_WITH_DEBT`
- **Work Item state:** `ACHIEVED`
- **Baseline commit:** `fb99621a58dbec60cd1354960f8e6675dfe3f507`
- **Current objective:** 将独立的实验协议验证函数和专用常量抽取到包内模块，同时保持所有行为、接口、错误文本、预算和 Transport 执行结果不变。

## Acceptance criteria

- `unresolved_required_values`、`assess_experiment_protocol`、`validate_experiment_report` 及其专用常量只有一个权威定义，并由 `opencli_transport.py` 兼容性重新导出。
- 三个函数的控制流、条件、返回结构、错误文本和默认值与基线 AST 等价。
- 新模块可独立按绝对路径导入；Transport 仍支持直接执行、现有 `importlib` 加载和 Skill 包复制后的任意绝对路径。
- `opencli_transport.py` 不超过 1350 行，新模块保持 250–350 行，Runtime 职责类别从六类降至五类。
- 所有现有纯本地协议与 Transport 测试继续通过；不运行真实 OpenCLI 或 Browser，不发送消息，不 commit 或 push。

## Completed

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

- 高复杂度协议函数只是被隔离，尚未简化。
- `opencli_transport.py` 仍约 1325 行。
- `send_command` 等状态机热点尚未处理。

## Decisions pending

- None.

## Next action

- 完成经用户授权的本地 Commit；提交验证通过且工作区干净后，开始只读 `COMPLEXITY-DELTA-002` 复测。

## Files to read

- `AGENTS.md`
- `README.md`
- `docs/index.md`
- `docs/specs/research-review-loop.md`
- `skills/research-review-lead/SKILL.md`
- `skills/research-review-lead/scripts/experiment_protocol.py`
- `skills/research-review-lead/scripts/opencli_transport.py`
- `scripts/test_opencli_transport.py`
- `scripts/check_skill_package.py`

## Last validation

- **Command:** `python -m unittest -v scripts.test_check_skill_package`
- **Result:** Passed all 9 standard unittest cases.
- **Command:** `python scripts/test_opencli_transport.py`
- **Result:** Passed all 101 directly invoked pure-local Transport tests.
- **Command:** `python scripts/check_skill_package.py`
- **Result:** Passed; controlled Runner called all 101 discovered tests exactly once, package version `0.4.11`.
- **Command:** `python scripts/check_docs.py`
- **Result:** Passed; 14 registered Markdown files.
- **Command:** direct and copied-package `opencli_transport.py --help`, independent protocol and Transport `importlib` probes.
- **Result:** Passed without relying on repository cwd.
- **Scope:** 只允许纯本地测试与静态检查；不运行真实 OpenCLI、Browser 实验或发送消息。
- **Last verified:** 2026-08-06
