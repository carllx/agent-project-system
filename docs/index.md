# Documentation Index

本文件是项目所有长期 Markdown 的唯一登记表。未登记的 Markdown 不属于项目知识系统。

| Path | Authority | Read when | Status | Last verified |
| --- | --- | --- | --- | --- |
| `AGENTS.md` | 每次任务的硬规则与安全边界 | 每次会话首先读取 | Active | 2026-08-05 |
| `README.md` | 项目身份、Browser 新对话 exact-ref bootstrap、当前阶段和入口 | 每次会话启动或跨 Browser Conversation 恢复 | Active | 2026-08-10 |
| `docs/index.md` | 长期 Markdown 唯一登记表 | 查找权威资料或创建文档前 | Active | 2026-08-11 |
| `docs/current.md` | 当前唯一 Work Item、Lab Evidence、下一动作与事实状态 | 每次会话启动及状态流转时 | Active | 2026-08-11 |
| `docs/references/current-execution-packet.md` | 当前 Execution Packet 的稳定 pointer；不保存 Packet 正文 | 新 Execution Agent 从当前 Work Item 定位精确执行契约时 | Active | 2026-08-11 |
| `docs/references/real-agent-review-loop-mvp-001-attempt-4.md` | Attempt 4 已批准的 self-contained Antigravity Execution Packet | 启动或审计 `REAL-AGENT-REVIEW-LOOP-MVP-001` Attempt 4 时 | Ready / Not started | 2026-08-11 |
| `docs/specs/system-governance.md` | 文档治理、信息分类与生命周期 | 修改治理、目录或文档类型时 | Active | 2026-08-05 |
| `docs/specs/agent-collaboration-protocol.md` | ACF 通用 Review Trigger、Contract、Decision、Completion Authority 与 Review Artifact access path | 设计、实现或验证任何 Agent Collaboration Review 流程时 | Candidate | 2026-08-09 |
| `docs/specs/antigravity-completion-gate-adapter.md` | Antigravity Completion-Gate Adapter 的状态映射、Contract、bounded continuation 与失败语义 | 设计、实现或验证 Antigravity execution termination gate 时 | Active | 2026-08-09 |
| `docs/specs/opencli-session-discovery.md` | OpenCLI Session Discovery、Conversation identity、投递验证与 exact-ID recovery 的产品 Contract | 设计、实现或验证 Browser/OpenCLI Session identity 时 | Candidate | 2026-08-09 |
| `docs/specs/research-review-loop.md` | RR Loop 的角色、canonical Browser message、受限 Product command path、ACF compatibility bridge、状态、交接与 OpenCLI 当前实现映射 | 执行或修改 RR Loop 时 | Active | 2026-08-11 |
| `docs/adr/0001-general-system-with-modular-workflows.md` | 通用系统与模块化工作流的架构决定 | 质疑项目定位或模块边界时 | Accepted | 2026-08-05 |
| `docs/adr/0002-self-contained-user-level-rr-lead-skill.md` | RR Lead 自包含用户级 Skill 的打包与部署决定 | 修改 RR Lead 包结构、安装或分发策略时 | Accepted | 2026-08-05 |
| `docs/adr/0003-agent-collaboration-framework.md` | Agent Collaboration Framework 与 IDE/Transport 解耦的长期架构决定 | 质疑系统定位、IDE/Transport 边界或框架分层时 | Accepted | 2026-08-08 |
| `docs/adr/0004-antigravity-completion-gate-adapter.md` | ACF Completion Authority 与 Antigravity execution termination 解耦的架构决定 | 质疑 Completion Gate、Stop Hook 或 Transport 边界时 | Accepted | 2026-08-09 |
| `skills/research-review-lead/SKILL.md` | RR Lead 模块的操作准则与当前 OpenCLI Evidence 边界 | 调用或维护 RR Lead 模块时 | Active | 2026-08-09 |
| `skills/research-review-lead/assets/context-packet.md` | Context Packet 可复用模板 | 首次向 RR Lead 同步 Work Item 时 | Active | 2026-08-05 |
| `skills/research-review-lead/assets/evidence-packet.md` | 通用 Evidence Packet 可复用模板 | 向 RR Lead 返回跨项目执行或调研证据时 | Active | 2026-08-05 |
| `skills/research-review-lead/assets/decision-request.md` | Decision Request 可复用模板 | 触发用户决策闸口时 | Active | 2026-08-05 |
| `skills/research-review-lead/assets/handoff.md` | Handoff 可复用模板与 exact-ref recovery locator | 对话不再可靠继续且需要接力时 | Active | 2026-08-09 |
| `skills/research-review-lead/assets/rr-lead-init.md` | Browser RR Lead 初始化与 GitHub exact-ref bootstrap 规则 | 创建或恢复真实 Browser RR Lead 对话时 | Active | 2026-08-09 |
| `skills/research-review-lead/scripts/opencli_transport.py` | OpenCLI 单次发送、恢复、去重和有限轮询的当前实现 | 通过 OpenCLI 发送、恢复、清理或审计 Session identity 时 | Active | 2026-08-09 |
