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

Agent Project System 的北极星是一套与具体 IDE 和 Transport 解耦的 **Agent Collaboration Framework**，使 Browser Lead 与 IDE Agent 能通过可定义、可观察、可恢复、可审查、可测试的协议形成长期工作闭环。它既不是单独的 RR Lead Skill，也不是 OpenCLI Transport。

目标关系：

```text
Agent Project System
→ Agent Collaboration Framework
→ Browser Lead / IDE Agent Collaboration Protocol
→ Runtime / Orchestration
→ Transport / IDE Adapters
```

角色与边界：

- **Browser Lead：** 负责规划、架构、Review 和被授权范围内的技术判断。
- **用户：** 保留目标、范围、权限、风险、成本和重要产品方向的最终决定权。
- **参考 IDE 顺序：** Antigravity 为第一参考 IDE；Codex 后续用于跨 IDE 通用性验证。
- **OpenCLI：** 只是 Transport Adapter，不等于整个系统。
- **rr-lead-skill-lab：** 独立实验环境，不是正式产品源码仓库。

`research-review-lead`（RR Lead Loop + 确定性 bootstrap + manual-export fallback）是本系统的第一个正式运行模块，但不等于整个系统。后续能力在完成登记和验证后逐步加入。

IDE-independent Completion-Gate Policy 位于 `runtime/`，正式 IDE Adapter 位于 `adapters/`。具体 Adapter 只负责把 Contract 翻译为目标 IDE 的 runtime/lifecycle 行为；Antigravity Completion-Gate 是第一版实现，未来 Codex Adapter 必须使用 Codex 可验证的对应机制，而不是复用 Antigravity schema。

本仓库是 `research-review-lead` 的开发和唯一手工维护源。源 Skill 包位于 `skills/research-review-lead/`，包含运行说明、版本和 Packet 资产。安装副本只是由源包生成的部署产物，不应手工编辑；目标项目无需克隆本仓库，也不必采用本仓库的治理目录。

## 当前阶段

已完成第一版信息架构迁移、RR Lead 自包含源包重构、确定性 bootstrap、manual-export fallback，以及 Reliable Product Transport MVP-0。当前源包 VERSION `0.4.18`；本机观察到的安装副本仍为 VERSION `0.4.15`，位于 `C:\Users\carll\.codex\skills\research-review-lead`，但项目证据尚不能把该本机路径证明为所有平台通用的 canonical 部署规范。首个真实 RR Loop 已完成（`FIRST-USE-LOOP-001`，`FIRST_USABLE_VERSION: 0.4.14`）。

ACF Protocol v0.1、第一版 Antigravity Completion-Gate Adapter 与 `OPENCLI-SESSION-DISCOVERY-001` 均已完成。Reliable Product Transport MVP-0 已通过 194 项 regression 和一次真实两消息同 Conversation E2E；状态为 `TRANSPORT_IMPLEMENTATION_READY=YES`、`TRANSPORT_REGRESSION_READY=YES`、`TRANSPORT_REAL_E2E_VALIDATED=YES`，并冻结为 `FROZEN_AT_MVP_0`。timeout recovery 和无额外 Conversation 副作用仍为非阻塞 `UNVERIFIED`。当前唯一 Active Product Work Item 是 `REAL-AGENT-REVIEW-LOOP-MVP-001`：把现有 Protocol、Completion Gate、冻结的 Transport 与 Browser Review 串成一次 `Execute → Review → Revise → Review → Approve` 的真实 Agent Review Loop MVP。最小 Product bridge 已位于 `runtime/review_loop.py`，原子 state driver 位于 `scripts/acf_review_loop.py`；它们只接收冻结 Transport 已验证的 Browser response，不改变 Completion Authority。当前状态是 `REAL_LOOP_READY=YES / WORK_ITEM_STATE=IN_PROGRESS`：可以启动真实 Antigravity/Browser 两轮 E2E，但尚未用本地结果模拟 Browser Review。GitHub Review Branch + Commit SHA 是 Browser 可访问时优先采用的 Review Artifact access path，但 GitHub 不承担 Completion Authority 或实时 Transport。

## 阅读入口

新会话按以下顺序加载上下文：

1. [`AGENTS.md`](./AGENTS.md)：每次任务都必须遵守的硬规则。
2. [`README.md`](./README.md)：项目定位与当前范围。
3. [`docs/index.md`](./docs/index.md)：长期知识的唯一登记表。
4. [`docs/current.md`](./docs/current.md)：当前唯一 Work Item 与事实状态。
5. 根据 Index 的 `Read when` 读取相关 Spec、ADR、Skill 或模板。

## 第一版范围

普通 Git 和 GitHub 远端可用于保存代码与历史。第一版不开发 GitHub Issues、Projects、自动同步或通知集成，也不开发多任务调度、图形界面或自动文件上传。

文档治理检查：

```bash
python scripts/check_docs.py
```

RR Lead 源包检查：

```bash
python scripts/check_skill_package.py
```
