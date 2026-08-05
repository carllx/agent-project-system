# Current Project State

## Project identity

- **Name:** Agent Project System
- **Repository root:** `E:\PROJECTS\agent-project-system`
- **Remote:** `https://github.com/carllx/agent-project-system.git`
- **Branch:** `main`

## Active Work Item

- **ID:** `TRANSPORT-A2P1-PRECONDITION-010`
- **Name:** 机器强制 A2.1 起始条件
- **Work Item state:** `IN_PROGRESS`
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
- 已增加公开 CLI 覆盖及既有发送回归；未运行真实 Browser 或真实发送。

## In progress

- 完成全套验证、源 Commit、Lab 整包同步与一致性核验。

## Blockers

- None.

## Decisions pending

- None.

## Next action

- 运行全套本地验证并审查 Diff；通过后创建本地实现 Commit、同步 Lab，再记录最终证据。

## Files to read

- `AGENTS.md`
- `README.md`
- `docs/index.md`
- `docs/specs/research-review-loop.md`
- `skills/research-review-lead/SKILL.md`
- `skills/research-review-lead/scripts/opencli_transport.py`
- `scripts/test_opencli_transport.py`

## Last validation

- **Status:** Pending final validation.
- **Scope:** 源包与纯本地公开 CLI 假 OpenCLI/Mock 验证；不运行真实 Browser 实验或真实发送。
- **Last verified:** 2026-08-05
