# Current Project State

## Project identity

- **Name:** Agent Project System
- **Repository root:** `E:\PROJECTS\agent-project-system`
- **Remote:** `https://github.com/carllx/agent-project-system.git`
- **Branch:** `main`

## Active Work Item

- **Name:** 修复新对话错投并收紧 Transport 实验纪律
- **Work Item state:** `ACHIEVED`
- **Baseline commit:** `8a85927d52d12b85acc98f79b7b02d18063717a5`
- **Current objective:** 增加 `MISROUTED_DELIVERY`，将新 Conversation 的创建、验证与发送拆开，限制恢复和实验预算，并用纯本地合成测试后重新发布 Lab 包。

## Acceptance criteria

- 只读取 `TRANSPORT-RECOVERY-002` 的 state、相关 raw 与最终缺陷结论，不再发送或扫描无关 Browser 对话。
- 旧 Conversation 精确命中进入 `MISROUTED_DELIVERY`、阻止重发和正式 RR 输出并返回 `BLOCKED`。
- 新发送遵循 `CREATE_NEW_CONVERSATION → VERIFY_NEW_CONVERSATION → SEND_MESSAGE`，未知页面状态不发送。
- 恢复只检查当前活动 Conversation 与有限最近候选，只搜索精确 Work Item ID 和 Message ID。
- Runtime 保存要求的身份、计数、时间、错投和停止字段。
- Skill 与测试规范包含有限命令预算和实验 Agent 硬边界。
- 六个纯本地合成场景、文档、包与 whitespace 验证通过。
- 创建本地 Commit、不 push，并完整替换 Lab Skill，证明包一致、无额外文件、fixture 不变。

## Completed

- 确认旧 Wrapper 排除所有 pre-send Conversation，无法把旧对话中的已送达消息分类为错投。
- 确认 OpenCLI `1.8.6` 的 `new` 只声明 `Status` 输出，而 `status` 可返回当前 URL、`read` 可核验空页面。
- 源包升级为 `0.4.0`，拆分创建、验证、发送流程；真实 Work Item 不再使用 `ask --new`。
- 增加 `MISROUTED_DELIVERY`、最少错投证据、正式回复隔离、同 Message ID 一次发送和有限恢复。
- 默认预算为一次发送、一次恢复、一次 detail、八个外部命令和六十秒。
- 增加六个纯本地合成场景和实验协议违规硬失败规则。
- 保留原 Goal Contract；正式 Loop 继续要求 A2、A3 先通过、至少两个完整审查循环和全部验收条件 `MET`。

## In progress

- None.

## Blockers

- 正式 Loop 仍被 Transport A2、A3 的真实 Browser 验证阻塞；本次被污染实验不能作为通过证据。

## Decisions pending

- None.

## Next action

- 使用新的 Work Item ID、Message ID 和 Runtime 目录运行一次严格受预算约束的 A2；如自动空白页验证失败，使用人工打开空白 ChatGPT 根 URL 的降级流程。A2 通过后再单独设计 A3。

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
- **Result:** Passed six pure-local transport scenarios without Browser sends.
- **Command:** `python scripts/check_docs.py`
- **Result:** Passed.
- **Command:** `python scripts/check_skill_package.py`
- **Result:** Passed.
- **Command:** `git diff --check`
- **Result:** Passed.
- **Scope:** Source and synthetic validation only; A2, A3 and formal Loop remain unverified.
- **Last verified:** 2026-08-05
