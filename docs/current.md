# Current Project State

## Project identity

- **Name:** Agent Project System
- **Repository root:** `E:\PROJECTS\agent-project-system`
- **Remote:** `https://github.com/carllx/agent-project-system.git`
- **Branch:** `main`

## Active Work Item

- **Name:** 修正 OpenCLI 传输等待机制并建立共同目标循环
- **Work Item state:** `ACHIEVED`
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
- 已创建本地源 Commit `de1dd6d6f051e75e770c53fbdc62959c2d9e51f2`，未 push。
- 已删除旧 Lab 包并从新源 Commit 整包复制；源与 Lab 均为八个文件、版本 `0.3.0`，路径和字节一致。
- 已确认源/实验包聚合哈希均为 `c494e14df9a21b6770fb03d6b4cc087345c9f10228d7138dc9f1c059d10bb9c4`，十个业务 fixture 同步前后聚合哈希均为 `ae3421e00eb49289cfe6c901ad66804180b6f21500bdacddba5f734f44025de6`。

## In progress

- None.

## Blockers

- None.

## Decisions pending

- None.

## Next action

- 在用户授权后运行单一新 `MESSAGE_ID` 的 one-send Transport Smoke Test；先不测试仍为 `UNVERIFIED` 的 `opencli chatgpt send` 候选。

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
- **Command:** source/Lab package byte comparison and canonical aggregate hash
- **Result:** Passed; eight paths and all bytes equal, no extra files, both hashes `c494e14df9a21b6770fb03d6b4cc087345c9f10228d7138dc9f1c059d10bb9c4`.
- **Command:** Lab fixture pre/post aggregate comparison
- **Result:** Passed; ten files, unchanged hash `ae3421e00eb49289cfe6c901ad66804180b6f21500bdacddba5f734f44025de6`.
- **Scope:** Source and non-mutating synthetic validation; the new one-send write path and `send` candidate remain unverified pending an authorized experiment.
- **Last verified:** 2026-08-05
