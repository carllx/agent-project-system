# Current Project State

## Project identity

- **Name:** Agent Project System
- **Repository root:** `E:\PROJECTS\agent-project-system`
- **Remote:** `https://github.com/carllx/agent-project-system.git`
- **Branch:** `main`

## Active Work Item

- **ID:** `TRANSPORT-SEND-READ-COMPAT-024`
- **Name:** 统一 send 与 prepare-new 的空页面解析
- **Work Item state:** `ACHIEVED`
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

- None.

## Completed

- 50 项纯本地 Transport 测试首轮全部通过；原 45 项与新增 5 项均通过。
- 已实现唯一共享 `classify_chatgpt_read_result`、manual-new-url 有界序列、发送计数调用边界和 Browser 副作用字段。
- 已加入与真实 A2.2 `raw/04-read-new.json` 逐字节相同的 `EMPTY_RESULT + exit 66` 回归 fixture；文件 SHA-256 均为 `c99007ba1f1b43467af27f886f7a1cb39ef5c49047907a7d0c17681f02ddf97d`。
- 已通过 50 项 Transport、文档治理、0.4.6 包检查、源/Lab Skill Creator 和 whitespace 校验。
- 已创建本地实现 Commit `a15b74e4145715ec5bd37c3ed01c9e05e99dd601`，未 push。
- 已逐文件覆盖同步权威源包到 `E:\PROJECTS\rr-lead-skill-lab\.agents\skills\research-review-lead`；源/Lab 均为 0.4.6、各 8 文件、路径差异和字节差异均为 0，规范包哈希均为 `65b146f6091ecb005715fbbee60b3c2b8d2476f004004cc38e779ff2b1a9e121`。
- 同步操作未以 `.runtime` 为目标；在禁止扫描其他 Runtime 的边界内，指定 `TRANSPORT-A2P2-023` 的 6 文件路径和逐文件 SHA-256 与同步前完全一致。

## Blockers

- None.

## Decisions pending

- None.

## Next action

- 使用新的 Work Item ID、Message ID 和 Runtime 目录重跑正式 A2.2：由用户预先打开 `https://chatgpt.com/new`，调用 `send --manual-new-url https://chatgpt.com/new`，验证单次真实发送和身份恢复；不得复用或修改 `TRANSPORT-A2P2-023`。

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
- **Command:** source/Lab relative-path manifest, per-file SHA-256 comparison, and canonical package hash
- **Result:** Source/Lab versions are `0.4.6`; both contain 8 files; path and byte diff counts are zero; both canonical hashes are `65b146f6091ecb005715fbbee60b3c2b8d2476f004004cc38e779ff2b1a9e121`.
- **Command:** authorized `TRANSPORT-A2P2-023` relative-path and per-file SHA-256 comparison before/after sync
- **Result:** All 6 authorized Runtime files are unchanged; path and content diff counts are zero.
- **Scope:** 仅使用指定 Runtime 的脱敏 fixture 与假 OpenCLI；未运行 OpenCLI、真实 Browser 实验或发送消息。
- **Last verified:** 2026-08-05
