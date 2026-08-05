# ADR 0001: General System with Modular Workflows

- **Status:** Accepted
- **Date:** 2026-08-05

## Context

迁移前仓库以 RR Lead 多 Agent 协作骨架为主体。该骨架包含有价值的角色边界、循环、Packet 和状态原则，但不足以承载治理、初始化和持续推进多种 Agent 项目的总目标。

## Decision

- 本项目定位为通用 Agent Project System，而不是单一 RR Lead 工具。
- Research Review Lead Loop 是第一个正式运行模块。
- 后续能力以登记、评审和验证后的模块逐步增加。
- 系统治理层、运行模块层和模板资产层必须分离；实际运行产生的临时内容不进入长期知识系统。
- 第一版只建立最小信息架构和文档治理，不一次实现所有模块。

## Consequences

旧骨架作为 Git 基线保留，其有效知识迁入新的权威位置。新增长期文档和模块必须经过登记与检查；这会增加少量治理成本，但能避免重复事实源和无序文件积存。
