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

Agent Project System 建立了一套解耦、可观察、可恢复、且保留 Browser Review Authority 的 **Minimal Browser Review Bridge**，使 IDE Agent（通过 Antigravity `/goal` 等 outer loop）能通过 OpenCLI 与 ChatGPT 中的 Browser Review Lead 进行确定的代码与架构审查闭环。

目标关系：

```text
Agent Project System
→ Antigravity /goal (Outer Execution & Continuation Loop)
→ Minimal Browser Review Bridge (opencli_transport.py / minimal_bridge.py)
→ OpenCLI
→ Browser Review Lead (ChatGPT)
```

角色与边界：

- **Browser Review Lead：** 负责规划、架构、Review、验证判定和被授权范围内的技术指导。
- **IDE Execution Agent：** 在目标项目中执行具体编码、验证与测试，并通过 Minimal Bridge 提交 Review Request。
- **用户：** 保留目标、范围、权限、风险、成本和重要产品方向的最终决定权。
- **OpenCLI：** 外部 Transport Adapter。

本仓库是 `research-review-lead` 的开发和唯一维护源。源 Skill 包位于 `skills/research-review-lead/`。

## 当前阶段

当前源包 VERSION `0.4.21`。已完成 Minimal Browser Review Bridge 架构精简，将外部执行与重试循环完全交由 Antigravity `/goal` 管理，本仓库仅维护轻量、确定、原子且支持 `--wait false` 快速返回与只读 Reconcile 的 Browser Review Bridge。冗余的二次 Review Loop、Completion Gate 以及巨型测试套件已移除。

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
