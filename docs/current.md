# Current Project State

## Project identity

- **Name:** Agent Project System
- **Repository root:** `E:\PROJECTS\agent-project-system`
- **Remote:** `https://github.com/carllx/agent-project-system.git`
- **Branch:** `main`

## Active Work Item

- **Name:** 修正 OpenCLI 传输等待机制并建立共同目标循环
- **Work Item state:** `IN_PROGRESS`
- **Baseline commit:** `1e30fb6543dc62a032fd4bb5aab859eef57beff5`
- **Current objective:** 从 `TRANSPORT-SMOKE-001` 的只读取证修正 timeout、投递恢复、消息幂等、有限等待与共同验收循环，并发布可重新同步到实验项目的自包含 Skill 包。

## Acceptance criteria

- 两次 timeout 对应的对话数量、身份、回复状态、重复情况和可恢复性由只读 history/detail 证据确认。
- Skill 使用明确的 Delivery State，不把 timeout 自动当作失败或触发重发。
- 每条 Browser 消息携带 Work Item、Message ID、Round 和 Message Type，并在发送前后去重。
- 发送与读取拆成单次发送、身份捕获或恢复、有限轮询和回复解析。
- Context、Evidence 与 Browser 初始化规则共享同一 Goal Contract 和逐项验收状态。
- 正式 transport wrapper 不保存凭据、不无限等待、不依赖 IDE 私有 scratch 路径。
- 文档、包检查、Skill 校验和 Git whitespace 验证通过。
- 验证后创建本地 Commit，不 push；随后完整替换实验包并证明包哈希一致、无额外文件、fixture 不变。

## Completed

- 已从 OpenCLI `1.8.6` 本机帮助确认 history、detail、ask 和 send 的参数形状。
- 已只读定位两个 `TRANSPORT-SMOKE-001` 对话；两个消息和 Browser 回复均存在且已完成，显式 ID detail 均可恢复。
- 已确认重试创建一个额外重复对话；timeout 发生在已创建、已投递之后的等待完成检测或结果返回边界。
- 已确认 CLI detail/history 不提供本次消息和回复的精确时间戳，不虚构时刻。
- 已实现 Skill `0.3.0` 的 Delivery State、Message ID 去重、Goal Contract、有限等待和 transport wrapper。
- 已用不发送消息的合成测试确认回复稳定阈值和状态转换，并通过全部源包静态验证。

## In progress

- 创建授权的本地源 Commit，然后整包替换并核验 Lab 副本。

## Blockers

- None.

## Decisions pending

- None.

## Next action

- 提交已验证的源变更，随后整包同步 Lab 并核验 fixture 未变化。

## Files to read

- `AGENTS.md`
- `README.md`
- `docs/index.md`
- `docs/specs/research-review-loop.md`
- `skills/research-review-lead/SKILL.md`
- `skills/research-review-lead/scripts/opencli_transport.py`

## Last validation

- **Command:** `python scripts/check_docs.py`
- **Result:** Passed; 14 registered Markdown files and repository layout valid.
- **Command:** `python scripts/check_skill_package.py`
- **Result:** Passed; exact eight-file package, five assets, wrapper syntax, portability and loop markers valid.
- **Command:** Skill Creator `quick_validate.py skills/research-review-lead`
- **Result:** Passed.
- **Command:** synthetic transport assertions
- **Result:** Passed; Message ID response classification, three-second stability threshold and state transitions valid without sending Browser messages.
- **Command:** `git diff --check`
- **Result:** Passed.
- **Scope:** Source and non-mutating synthetic validation; the new one-send write path and `send` candidate remain unverified pending an authorized experiment.
- **Last verified:** 2026-08-05
