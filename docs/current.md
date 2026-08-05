# Current Project State

## Project identity

- **Name:** Agent Project System
- **Repository root:** `E:\PROJECTS\agent-project-system`
- **Remote:** `https://github.com/carllx/agent-project-system.git`
- **Branch:** `main`

## Active Work Item

- **ID:** `TRANSPORT-INTEGRATED-SEND-027`
- **Name:** 整合 START_NEW_AND_SEND
- **Work Item state:** `ACHIEVED`
- **Baseline commit:** `68b519c1446d23a1bb0db93e4f35228c49362318`
- **Current objective:** 停止拆分 A2.1/A2.2 微型实验，以单一 Wrapper 调用完成新对话创建、验证、单次发送、身份捕获和有界恢复。

## Acceptance criteria

- 提供显式 `send --prepare-new` 单一命令，不使用 `ask --new`，不要求用户预先打开 `/new`。
- 同一调用内保存有限 history 基线、调用一次 `new`、验证 `/new` 或根 URL、验证 read 为空、调用一次 ask、解析身份并检查发送后 status。
- 仅在必要时执行一次 post-send history 差集与最多一次 detail。
- 同一 Message ID 最多发送一次，保留 `MISROUTED_DELIVERY`、`DELIVERY_UNKNOWN` 与禁止重发。
- 不新增文档体系，只增加整合路径必要的本地测试。
- 版本升级、完整验证、Lab 整包同步和源/Lab 一致性通过；不运行真实 Browser、不 push。

## Confirmed implementation

- `send --prepare-new` 将正式操作记录为 `operation=START_NEW_AND_SEND`、`prepare_new=true`。
- 正常明确身份路径的命令序列为 `history → status → new → status → read → ask → status`；ask 只调用一次，post-send history 和 detail 不运行。
- 身份缺失的恢复路径在上述序列后追加一次 `history → detail`，总外部命令数为 9，`recovery_attempt_count=1`、`detail_check_count=1`。
- 集成调用先保存有限 history 基线，再记录发送前活动 URL；无需用户操作 Browser 页面。
- ask 明确 ID 与发送后 status 一致时直接完成；身份缺失、传输错误或身份冲突时才进入既有有界恢复。
- 发送前 new、URL 或 empty-read 验证失败时在 ask 前停止，两个发送计数保持零。
- 相同 Message ID 的第二次 integrated send 在任何新外部命令前被永久拒绝。
- standalone `prepare-new` 与 `--manual-new-url` 仅保留兼容和本地诊断，不再是正式实验前置步骤，也不得要求用户使用。

## Completed

- 版本升级为 `0.4.8`。
- 75 项纯本地 Transport 测试全部通过，其中只新增整合入口 help、单调用成功路径和必要的一次恢复路径；既有 same-ID 重发测试改为覆盖 integrated path。
- 文档治理、包检查、Skill Creator 和 whitespace 校验通过。
- 源 Skill 包已整包同步到 `E:\PROJECTS\rr-lead-skill-lab\.agents\skills\research-review-lead`，源/Lab 文件与字节一致。
- 未运行真实 OpenCLI 或 Browser，未发送消息，未 push。

## Blockers

- None.

## Decisions pending

- None.

## Next action

- 只安排一次最终真实端到端实验：使用新的 Work Item ID、Message ID 和 Runtime 调用 `send --prepare-new`。如果在现有有限预算内仍不能得到明确 Conversation ID 和回复，停止继续修补 OpenCLI 1.8.6 Transport，并把该路线标记为当前不可可靠使用；不得再拆分 A2.1/A2.2 或新增延长验证的 Work Item。

## Files to read

- `AGENTS.md`
- `README.md`
- `docs/index.md`
- `docs/specs/research-review-loop.md`
- `skills/research-review-lead/SKILL.md`
- `skills/research-review-lead/scripts/opencli_transport.py`
- `scripts/test_opencli_transport.py`

## Last validation

- **Command:** `python scripts/test_opencli_transport.py`
- **Result:** Passed 75 pure-local scenarios, including both integrated START_NEW_AND_SEND paths and existing transport regressions.
- **Command:** `python scripts/check_docs.py`
- **Result:** Passed; 14 registered Markdown files.
- **Command:** `python scripts/check_skill_package.py`
- **Result:** Passed for version `0.4.8` and the exact eight-file package.
- **Command:** Skill Creator `quick_validate.py` for source and Lab packages
- **Result:** Passed for both packages.
- **Command:** `git diff --check`
- **Result:** Passed; only Git line-ending conversion warnings were emitted.
- **Scope:** 只使用纯本地 fake OpenCLI 与静态检查；未运行真实 OpenCLI、Browser 实验或发送消息。
- **Last verified:** 2026-08-05
