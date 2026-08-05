# Current Project State

## Project identity

- **Name:** Agent Project System
- **Repository root:** `E:\PROJECTS\agent-project-system`
- **Remote:** `https://github.com/carllx/agent-project-system.git`
- **Branch:** `main`

## Active Work Item

- **ID:** `TRANSPORT-A2P1-INTERFACE-004`
- **Name:** 补齐 A2.1 可执行接口
- **Work Item state:** `ACHIEVED`
- **Baseline commit:** `b80072da113e119336fb8acd298ebf5456e66f09`
- **Current objective:** 为 Transport Wrapper 增加正式、独立、零发送的 `prepare-new` 命令，以机器预算完成新对话创建、验证、Runtime 持久化和停止。

## Acceptance criteria

- 公开 CLI `prepare-new --runtime-dir <path> --work-item-id <id>` 可独立执行 A2.1。
- 记录操作前 URL、旧 Conversation ID、操作后 URL、验证与只读结果。
- 一次 `new` 后必须离开旧 `/c/<id>`，停在允许的 ChatGPT 根页面或 `/new`，且 `read` 为空。
- `EMPTY_RESULT` 在 A2.1 中作为空页面成功证据；不调用 `ask`、`send`，不创建 Message ID。
- Wrapper 内强制零发送、零恢复、零 detail、最多四个外部命令和端到端六十秒。
- Runtime 保存指定字段，预算耗尽时记录 `stop_reason=BUDGET_EXHAUSTED`。
- 合成测试全部通过公开 CLI，覆盖帮助、成功、旧对话、已有消息、零发送、时间预算、持久化和命令预算。
- Skill、Spec 和当前状态明确 `prepare-new=A2.1`、`send=A2.2/A3`，版本为 `0.4.1`。
- 创建本地 Commit、不 push；完整覆盖同步 Lab Skill，证明源/Lab 包哈希一致且 fixture 不变。

## Completed

- 已确认上一 Work Item 完成且工作区起始状态干净。
- 已实现公开 `prepare-new`、独立 Runtime schema、`EMPTY_RESULT` 语义和零发送机器预算。
- 已将合成测试改为通过 subprocess 调用公开 CLI，并使用纯本地假 OpenCLI，未运行真实 Browser 实验。
- 已同步更新 Skill、RR Loop Spec、版本与包检查规则。
- 已通过 14 项纯本地传输测试、文档检查、包检查、Skill Creator 校验和 whitespace 检查。
- 已创建本地源 Commit `45e72b4a35a049192a70d3e47b9157a1bd542278`，未 push。
- 已完整替换 Lab Skill；源与 Lab 均为八个文件，路径和聚合哈希 `7dda7442cec21a12388290ee53bf63f77f30b0397f8777f8ac4029808d5b273d` 一致。
- 已确认十个业务 fixture 同步前后聚合哈希均为 `c00493f07deab9264410b790ebc725dfc2b6ff3947272d489d0f8c8326835d61`；`.runtime` 未参与同步。

## In progress

- None.

## Blockers

- None.

## Decisions pending

- None.

## Next action

- 在独立 Work Item 中运行真实 Browser A2.1；本 Work Item 不运行真实 Browser 实验，也不证明 A2.2/A3。

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
- **Result:** Passed 14 pure-local scenarios: nine public A2.1 CLI cases and five send regressions; no real Browser calls or sends.
- **Command:** `python scripts/check_docs.py`
- **Result:** Passed.
- **Command:** `python scripts/check_skill_package.py`
- **Result:** Passed for version `0.4.1` and exact eight-file package.
- **Command:** Skill Creator `quick_validate.py skills/research-review-lead`
- **Result:** Passed.
- **Command:** `git diff --check`
- **Result:** Passed.
- **Command:** source/Lab canonical aggregate hash and fixture pre/post hash
- **Result:** Source/Lab paths and hash equal; ten fixtures unchanged.
- **Scope:** Source and pure-local public-CLI synthetic validation only; no real Browser experiment or message send.
- **Last verified:** 2026-08-05
