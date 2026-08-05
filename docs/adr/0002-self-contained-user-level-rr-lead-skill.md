# ADR 0002: Self-contained User-level RR Lead Skill

- **Status:** Accepted
- **Date:** 2026-08-05

## Context

RR Lead 的源 Skill 已能描述协作循环，但其模板位于仓库根目录，运行说明还依赖仓库 Spec。这使部署副本离开 `agent-project-system` 后无法独立运行，也会迫使普通目标项目了解开发仓库结构。

## Decision

- 将 `skills/research-review-lead/` 建成自包含源包，模板存入包内 `assets/`。
- `agent-project-system` 是唯一开发和手工维护源；安装副本只由源包部署。
- Codex 用户级目标位置采用 `$HOME/.agents/skills/research-review-lead`。
- 安装和更新不得静默覆盖未知修改，必须先显示和验证内容。
- Skill 不要求目标项目克隆源仓库、使用 Git 或采用 Agent Project System 治理结构。
- 当前实现只面向 Codex Skills；Gemini 和其他 IDE 兼容性不作承诺。
- 面向多人正式分发、市场安装和更广泛集成留到未来 Plugin 阶段，不进入当前 MVP。

## Consequences

模板从根目录迁入 Skill 包并成为唯一权威副本，运行路径可按 Skill 目录解析。源包增加独立版本和机械检查，后续安装器只负责受控复制、更新和卸载，不维护第二套内容。目标项目可以采用完整治理模式，也可以仅使用最小兼容协议。
