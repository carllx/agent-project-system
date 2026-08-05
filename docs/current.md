# Current Project State

## Project identity

- **Name:** Agent Project System
- **Repository root:** `E:\PROJECTS\agent-project-system`
- **Remote:** `https://github.com/carllx/agent-project-system.git`
- **Branch:** `main`

## Active Work Item

- **ID:** `TRANSPORT-A2P1-PRECONDITION-010`
- **Name:** 机器强制 A2.1 起始条件
- **Work Item state:** `ACHIEVED`
- **Baseline commit:** `0ae60e4ed4a6be17014a999186b1c74696eee647`
- **Current objective:** 为 `prepare-new` 增加机器强制的旧 Conversation 起始条件，避免从 `/new` 启动的无效转换实验。

## Acceptance criteria

- 公开 `prepare-new --help` 暴露 `--require-existing-conversation`。
- 正式 A2.1 从精确 ChatGPT `/c/<id>` 起始时继续执行 `new → status → read`，并兼容真实 `EMPTY_RESULT + exit code 66`。
- 严格模式从 `/new`、根 URL、其他域名或无效 Conversation URL 起始时，只执行最小只读 `status`，在 `new` 和 `read` 前返回 `BLOCKED_BEFORE_EXECUTION`。
- Runtime 保存前置条件、起始状态、`new` 调用、转换、空环境、停止原因和结果字段，所有场景保持 `message_send_count=0`。
- 未带新参数的普通 `prepare-new` 行为保持兼容，A2.2/A3 发送测试无回归。
- 只更新既有 Skill、Spec、Current 权威文档，版本升至 `0.4.3`。
- 完成本地验证、Commit（不 push）、Lab Skill 全量同步及源/Lab 包哈希核验；保留历史 Runtime，不运行真实 Browser 实验。

## Completed

- 已确认上一 Work Item 为 `ACHIEVED`、本项开始时工作区干净。
- 已确认根因为 Wrapper 只记录 `ALREADY_NEW`，却没有机器阻止无效的 A2.1 转换实验继续执行 `new`。
- 已实现严格起始闸门、所需 Runtime 字段和精确 Conversation URL 判断，并保留无参数兼容路径。
- 已通过 26 项纯本地公开 CLI 测试：21 项 `prepare-new` 场景和五项 A2.2/A3 `send` 回归；全部只驱动本地假 OpenCLI，未运行真实 Browser 或真实发送。
- 已通过文档检查、包检查、Skill Creator `quick_validate.py` 和 whitespace 检查，版本为 `0.4.3`。
- 已创建本地实现 Commit `64c51454a07e55855a865f9f11c4d918b15a1d53`，未 push。
- 已完整覆盖同步 Lab Skill；源与 Lab 均为八个文件且逐文件一致，规范包聚合哈希均为 `47af48427c5cfb019935b4dd265a5b86f46626f7e2dc6eb98d00df95ff4ce222`。
- 已核验 Lab 的 25 个历史 Runtime 文件同步前后清单与聚合哈希均为 `3e50ec6f166210082e8fdf4018a3c62df255ee996cd8656f185eb21fe3dde476`；业务 fixture 聚合哈希同步前后均为 `9c279be8baf45cc518bc12ce139dac1acb60e83726e8c0ab247e031fa604f867`。

## In progress

- None.

## Blockers

- None.

## Decisions pending

- None.

## Next action

- 在新的独立 Work Item 中，由用户预先停留在一个旧 ChatGPT `/c/<id>` 页面，然后使用 `prepare-new --require-existing-conversation --max-external-commands 4 --max-experiment-seconds 60` 运行真实 A2.1；实验 Agent 不得自行打开或搜索旧对话。

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
- **Result:** Passed 26 pure-local public-CLI scenarios: 21 `prepare-new` cases and five A2.2/A3 `send` regressions.
- **Command:** `python scripts/check_docs.py`
- **Result:** Passed.
- **Command:** `python scripts/check_skill_package.py`
- **Result:** Passed for version `0.4.3` and the exact eight-file package.
- **Command:** Skill Creator `quick_validate.py skills/research-review-lead`
- **Result:** Passed.
- **Command:** `git diff --check`
- **Result:** Passed; only Git line-ending conversion warnings were emitted.
- **Command:** source/Lab per-file manifest, canonical package hash, Runtime pre/post hash, and fixture pre/post hash comparison
- **Result:** Source/Lab paths and hashes equal; all 25 historical Runtime files and all business fixtures unchanged.
- **Scope:** 源包与纯本地公开 CLI 假 OpenCLI 验证；未运行真实 Browser 实验、未真实发送、未修改历史 Runtime。
- **Last verified:** 2026-08-05
