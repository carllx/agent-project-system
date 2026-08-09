# ADR 0003: Agent Collaboration Framework (decoupled from IDE and Transport)

- **Status:** Accepted
- **Date:** 2026-08-08

## Context

ADR-0001 已把系统定位为“通用 Agent Project System，而不是单一 RR Lead 工具”，并建立了模块化、登记与验证的工作流。但随着 RR Lead 与 OpenCLI Transport 的成熟，出现把整个项目误认为“OpenCLI Transport 项目”的风险：Transport 只是通信手段，不应决定系统身份或目标。

用户重新明确了上位目标：Agent Project System 最终要建设的是与具体 IDE 和 Transport 解耦的 Agent Collaboration Framework，而非单独一个 RR Lead Skill 或一个 OpenCLI Transport。

## Decision

- Agent Project System 的上位目标是一套与具体 IDE 和 Transport 解耦的 Agent Collaboration Framework。
- 目标关系按以下层次理解：

  ```text
  Agent Project System
  → Agent Collaboration Framework
  → Browser Lead / IDE Agent Collaboration Protocol
  → Runtime / Orchestration
  → Transport / IDE Adapters
  ```

- Browser Lead 负责规划、架构、Review 和被授权范围内的技术判断；用户保留目标、范围、权限、风险、成本和重要产品方向的最终决定权。
- 参考 IDE 顺序：Antigravity 为第一参考 IDE；Codex 后续用于跨 IDE 通用性验证。
- OpenCLI 只是 Transport Adapter，不等于整个系统。
- rr-lead-skill-lab 是独立实验环境，不是正式产品源码仓库。

## Relationship to ADR-0002

ADR-0002 继续作为 `research-review-lead` 自包含打包、源包权威、部署副本和安装边界的权威决定；本 ADR 不整体 Supersede ADR-0002。ADR-0002 中“当前实现只面向 Codex Skills”的表述描述的是 2026-08-05 的具体实现范围，不再代表 Agent Project System 的系统级目标或未来跨 IDE 兼容边界。ADR-0003 新增的是系统级 Agent Collaboration Framework 分层和 IDE/Transport 解耦决定。

ADR-0002 记录的 `$HOME/.agents/skills/research-review-lead` 是历史设计目标。本机当前实际存在且与源包九个文件逐一匹配的安装副本为 `C:\Users\carll\.codex\skills\research-review-lead`（VERSION `0.4.15`），因此它仅记为 `OBSERVED_LOCAL_INSTALL_PATH`。仓库没有安装脚本，也没有足够的项目内证据证明任一路径是当前跨平台 canonical Codex 用户级 Skill 路径；`CANONICAL_DEPLOYMENT_PATH: UNVERIFIED`。

## Consequences

- Transport 与协议、运行时、框架层分离：后续 Transport/IDE 适配变化不应改变框架协议与身份。
- 真实实验优先验证完整闭环（IDE Agent → Browser Review → Decision → IDE Execution → Evidence → Browser Result Review），而非单独证明 Transport 能收发。
- README、治理 Spec 与当前状态文档以框架为北极星，避免把项目误认为 Transport 项目。
