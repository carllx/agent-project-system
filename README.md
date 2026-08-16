# Agent Project System

## BROWSER_NEW_CONVERSATION_START_HERE

新 Browser Agent 的唯一外部入口：

```text
REPOSITORY: carllx/agent-project-system
START_HERE: README.md
```

必须从用户提供的 exact `HANDOFF_COMMIT_SHA` 读取本文件，再按以下顺序恢复项目：

1. `AGENTS.md`
2. `README.md`
3. `docs/index.md`
4. `docs/current.md`
5. 根据 `docs/index.md` 的 `Read when` 读取当前 Work Item 适用的 Spec、ADR、Skill 或模板

不得从旧聊天记忆猜测项目状态。GitHub exact ref 中的真实文件、当前状态和证据优先；`main` 不一定包含尚未完成的 Active Work Item。若 exact ref 不可读取或上述入口互相冲突，停止并把冲突报告给用户，不得自行补全。

Agent Project System 建立了一套解耦、可观察、可恢复、且保留 Browser Review Authority 的 **Agent Collaboration Framework**，使 IDE Agent 能与 ChatGPT 中的 Browser Review Lead 进行确定的代码与架构审查闭环。

### 架构与控制面状态

- **当前生产与回滚基线 (Production Baseline):** Minimal Browser Review Bridge（PR #3，冻结基线 SHA `d7651f95059694047d2a7e280afe761264a54058`）。
- **当前架构控制面候选 (Architecture Candidate):** APS Message Hub（[Issue #9](https://github.com/carllx/agent-project-system/issues/9) / [docs/specs/message-hub-control-plane-migration.md](docs/specs/message-hub-control-plane-migration.md)），作为 ADR-0003 中 Runtime / Orchestration 通信与事件控制面职责的候选实现。
- **当前阶段:** `CONTROL_PLANE_MIGRATION_PLANNING`（仅迁移架构规划，尚未授权生产代码迁移）。

目标关系（候选演进方向）：

```text
Agent Project System
→ Agent Collaboration Framework (ADR-0003)
→ Browser Lead / IDE Agent Collaboration Protocol
→ Message Hub Control Plane (Runtime / Orchestration 候选)
→ Transport / Browser Adapters (OpenCLI)
```

角色与边界：

- **Browser Review Lead：** 负责规划、架构、Review、验证判定和被授权范围内的技术指导。
- **IDE Execution Agent：** 在目标项目中执行具体编码、验证与测试，并通过控制面提交 Review Request。
- **用户：** 保留目标、范围、权限、风险、成本和重要产品方向的最终决定权。
- **OpenCLI：** 外部 Transport Adapter。

本仓库是 `research-review-lead` 的开发和唯一维护源。源 Skill 包位于 `skills/research-review-lead/`。

## 当前阶段

当前处于 **Message Hub 生产控制面迁移规划阶段**（`APS-MESSAGE-HUB-MIGRATION-001`）。Minimal Bridge 基线保持冻结与可用；Message Hub 已完成 Phase 2 PoC 验证并由 Browser 批准为候选控制面，当前仅开展架构设计与分阶段迁移规划，未授权直接合入或生产代码重写。

## 阅读入口

新会话按以下顺序加载上下文：

1. [`AGENTS.md`](./AGENTS.md)：每次任务都必须遵守的硬规则。
2. [`README.md`](./README.md)：项目定位与当前范围。
3. [`docs/index.md`](./docs/index.md)：长期知识的唯一登记表。
4. [`docs/current.md`](./docs/current.md)：当前唯一 Work Item 与事实状态。
5. 根据 Index 的 `Read when` 读取相关 Spec、ADR、Skill 或模板。

## 验证检查

文档治理检查：

```bash
python scripts/check_docs.py
```

Skill 源包检查：

```bash
python scripts/check_skill_package.py
```

Minimal Bridge 单元测试：

```bash
python -B -m unittest scripts/test_minimal_review_bridge.py
```
