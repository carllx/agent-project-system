# Current Project State

## Project identity

- **Name:** Agent Project System
- **Repository root:** `E:\PROJECTS\agent-project-system`
- **Remote:** `https://github.com/carllx/agent-project-system.git`
- **Branch:** `main`

## Active Work Item

- **ID:** `EXPERIMENT-EXECUTION-DISCIPLINE-014`
- **Name:** 禁止实验 Agent 无意义等待与占位符执行
- **Work Item state:** `IN_PROGRESS`
- **Baseline commit:** `b53615615956b18dce7e237ea52d39d27a347624`
- **Current objective:** 阻止实验 Agent 使用未解析占位符执行命令，并禁止同步命令完成后的 schedule、sleep、timer 或无意义轮询。

## Acceptance criteria

- 所有必填值在任何实验动作前验证；空值与已声明的占位符模式返回 `BLOCKED_BEFORE_EXECUTION: REQUIRED_VALUE_UNRESOLVED`，外部命令数为零。
- 同步 Shell 结果包含 exit code、stdout、stderr 后立即报告和结束；之后 schedule、sleep、timer、wait 或无意义轮询判为 `UNAUTHORIZED_IDLE_WAIT`。
- 只有明确异步未完成状态、可验证 Job ID、Work Order 轮询授权和预算同时存在时允许轮询。
- 默认 `MAX_IDLE_WAIT_SECONDS=0`、`MAX_SCHEDULE_CALLS=0`、`MAX_POLL_ATTEMPTS=0`，禁止站立等待输出。
- 实验动作和新增报告字段真实计数；纯本地测试覆盖用户要求的十类场景。
- 只更新既有 Skill、初始化资产、Spec、Current、Wrapper 和验证脚本，版本升至 `0.4.4`。
- 完成本地验证、Commit（不 push）、Lab Skill 整包覆盖同步及逐文件和包哈希核验；保留全部 Runtime，不运行真实 Browser 实验、不发送消息。

## Completed

- 已确认上一 Work Item 为 `ACHIEVED`、本项开始时工作区干净，基线为 `b53615615956b18dce7e237ea52d39d27a347624`。
- 已确认失败根因为实验协议没有在外部动作前强制验证占位符，也没有把同步 Shell 完成定义为立即终止条件。
- 已开始把占位符闸门、零等待默认值、唯一轮询例外、动作计数和必填报告字段写入既有权威位置与纯本地协议判定。

## In progress

- 完成代码与测试审查，运行全套本地验证。
- 创建本地实现 Commit、覆盖同步 Lab Skill、核验包一致性与 Runtime 保留，然后记录最终证据。

## Blockers

- None.

## Decisions pending

- None.

## Next action

- 完成协议实现和纯本地测试后，执行要求的验证；不运行真实 Browser 实验。

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
- **Scope:** 只运行纯本地假 OpenCLI 与合成协议轨迹；不运行真实 Browser 实验、不发送消息。
- **Last verified:** 2026-08-05
