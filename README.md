# Agent Collaboration System

本项目旨在建立一套不绑定具体模型的多 Agent 协作体系。

## 当前阶段

第一版（MVP）骨架搭建阶段。主要确立工作流、职责边界和基本原则。当前不涉及实际自动化代码的开发。

## 阅读入口

对于新加入本项目的 Agent，请务必按照以下顺序阅读项目文档：

1. **[`AGENTS.md`](./AGENTS.md)**: 项目入口、核心规则和优先级（**必须首先阅读**）。
2. **[`docs/PROJECT_CHARTER.md`](./docs/PROJECT_CHARTER.md)**: 项目长期宪章与基本原则。
3. **[`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md)**: 角色架构与边界。
4. **[`state/active-work-item.md`](./state/active-work-item.md)**: 查看当前工作状态。

## 暂不处理范围（第一版限制）

- 不接入 GitHub 集成。
- 不开发或使用自动文件上传功能。
- 不进行 Token 消耗的精确统计。
- 不支持多 Work Item 并行执行。
- 浏览器端不会主动控制 IDE 端。
- 不包含自动通知系统和图形界面。
- 不引入新的依赖或程序代码。
