# Agent Project System

Agent Project System 是一套通用的 Agent 项目系统，用于帮助不同类型的项目建立清晰的文档治理、唯一当前状态、可登记的运行模块，以及可持续推进的协作流程。

Research Review Lead Loop（RR Lead Loop）是本系统的第一个正式运行模块，但不等于整个系统。后续能力会在完成登记和验证后逐步加入，而不是在第一版一次铺开。

## 当前阶段

当前处于第一版信息架构与文档治理重构阶段。重点是建立权威文档、运行模块、模板资产和临时运行内容之间的边界；暂不开展真实自动协作实验。

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
