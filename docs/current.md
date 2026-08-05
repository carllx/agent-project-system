# Current Project State

## Project identity

- **Name:** Agent Project System
- **Repository root:** `E:\PROJECTS\agent-project-system`
- **Remote:** `https://github.com/carllx/agent-project-system.git`
- **Branch:** `main`

## Active Work Item

- **ID:** `TRANSPORT-SEND-READ-COMPAT-024`
- **Name:** 统一 send 与 prepare-new 的空页面解析
- **Work Item state:** `IN_PROGRESS`
- **Baseline commit:** `e42d21c13203f1162aad4681d32aed36c8bc09af`
- **Current objective:** 让 `send` 与 `prepare-new` 共享真实 OpenCLI `EMPTY_RESULT` 解析逻辑，并修正 manual-new-url 的调用和副作用语义。

## Acceptance criteria

- 只读取 `TRANSPORT-A2P2-023` 指定证据，不运行真实 Browser、不发送消息、不修改历史 Runtime。
- `prepare-new` 与 `send` 调用同一个空页分类器；精确 `EMPTY_RESULT` 允许出现在 stderr 且允许非零退出码。
- `send --manual-new-url` 使用首次 status 精确校验、有限 history、read 和单次 ask，不调用 `new`。
- 非空、未知错误和不可解析输出保守阻塞且发送计数保持零；实际写命令调用时两个发送计数才同时为一。
- Browser 副作用状态区分已在 `/new`、是否调用 `new` 和是否真的发生导航。
- 版本升至 `0.4.6`，现有恢复、幂等、A2.1、A2.2/A3 回归全部通过。
- 完成本地 Commit（不 push）、Lab Skill 整包同步和逐文件核验，历史 Runtime 保持不变。

## Confirmed facts

- 指定 `raw/04-read-new.json` 的 `returncode=66`、stdout 为空，stderr 是 OpenCLI error envelope 且错误码精确为 `EMPTY_RESULT`；原始分类为 `A. EXACT_EMPTY_RESULT`。
- 修改前 `prepare-new` 调用 `classify_read_result`，该函数能读取 stderr 的精确错误码；`send` 另用 `timed_out/returncode/result_rows(stdout)` 条件，仍要求退出码为零并未读取 stderr envelope。
- 真实 A2.2 因上述分叉在发送前错误停止；原 Runtime 的 `send_attempt_count=0`，且没有调用底层发送命令。
- 指定 Runtime 的六个文件已记录同步前逐文件路径、字节与 SHA-256；本轮不读取其他 Runtime。

## In progress

- 已实现共享 `classify_chatgpt_read_result`、manual-new-url 有界序列、发送计数调用边界和 Browser 副作用字段。
- 已加入真实 A2.2 `EMPTY_RESULT + exit 66` 脱敏精确结构 fixture 与 send 回归。
- 待完成全部治理/包/Skill Creator 校验、本地提交、Lab 整包同步与最终哈希核验。

## Completed

- 50 项纯本地 Transport 测试首轮全部通过；原 45 项与新增 5 项均通过。

## Blockers

- None.

## Decisions pending

- None.

## Next action

- 运行完整校验，审查 Diff，创建本地实现 Commit；随后整包同步到 Lab 并核验源/Lab 与指定 Runtime。

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
- **Result:** Passed 50 pure-local scenarios, including all prior 45 scenarios and five send/read compatibility regressions.
- **Command:** `python scripts/check_docs.py`
- **Result:** Passed; 14 registered Markdown files.
- **Command:** `python scripts/check_skill_package.py`
- **Result:** Passed for version `0.4.6` and the exact eight-file package.
- **Command:** `PYTHONUTF8=1` Skill Creator `quick_validate.py skills/research-review-lead`
- **Result:** Passed.
- **Command:** `git diff --check`
- **Result:** Passed; only Git line-ending conversion warnings were emitted.
- **Scope:** 仅使用指定 Runtime 的脱敏 fixture 与假 OpenCLI；未运行 OpenCLI、真实 Browser 实验或发送消息。
- **Last verified:** 2026-08-05
