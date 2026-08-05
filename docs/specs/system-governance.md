# System Governance Specification

## Purpose

Agent Project System 用于治理、初始化和持续推进不同类型的 Agent 项目。第一版优先建立能运行、能验证、能交接的最小治理骨架，不追求一次实现所有模块。

## Core principles

- **MVP 优先：** 首版先跑通核心治理流程。
- **单任务执行：** 第一版任何时刻只有一个 Active Work Item。
- **非阻塞管理：** 只有影响当前验收标准的问题才阻塞；其他发现记为 Debt。
- **闭环推进：** 每轮审查都要给出明确、可执行、可验证的下一步。
- **本地事实纠偏：** 真实文件、命令、测试和 Diff 可以纠正外部误判。

## Four content classes

1. **系统治理文档：** 定义系统身份、治理规则、架构决定和当前状态，全部登记在 `docs/index.md`。
2. **运行模块：** 系统可以实际采用的正式能力，例如 `skills/research-review-lead/SKILL.md`；不是普通说明，但必须登记。
3. **模板资产：** 随运行模块保存的可复用产品文件，例如 `skills/*/assets/`；模板可长期保存，填写后的实例默认是临时内容。
4. **临时运行内容：** 实际 Handoff、Packet、调查草稿、Session Summary、日期状态副本以及 `final`、`v2`、`backup` 等副本，不得进入仓库。

## Closed document types

长期 Markdown 只允许以下类型：

- `AGENTS.md`、`README.md` 和可选的根目录 `CLAUDE.md`
- `docs/index.md`、`docs/current.md`
- `docs/specs/*.md`、`docs/adr/*.md`、`docs/references/*.md`
- `skills/*/SKILL.md`、`skills/*/assets/*.md`

未登记的 Markdown 不属于项目知识系统。不得创建 `old`、`final`、`v2`、`backup`、日期 Handoff、Session Summary 或 Next Steps 文件来保存历史。

## Documentation gate and registry

`docs/index.md` 是所有长期 Markdown 的唯一登记表。创建文档前必须确认：允许的文档类型确有必要、不会形成重复事实源、路径与用途清楚，并在同一变更中登记。`scripts/check_docs.py` 负责机械检查，但不能替代内容判断。

## Sources of truth and lifecycle

- `docs/current.md` 是当前 Work Item 和交接事实的唯一来源。
- Spec 记录当前有效规则；ADR 记录长期架构决定及原因；Index 记录权威入口。
- 事实变化时原地更新权威文件，不创建版本副本。
- Git 是历史来源。提交历史保存被替换的路径与旧内容，无需仓库内副本。
- 过时内容先迁移有效知识和更新引用，再删除重复路径。
- 实际 Packet 或 Handoff 默认只作为消息传递；确需长期保存时必须获得用户明确批准并通过文档闸门。

## Modules, assets, and adapters

运行模块和随包模板资产是允许进入仓库的产品文件，但必须登记并保持边界清楚。工具适配文件只能作为薄适配层，引用现有权威文档；不得复制整套规则或成为新的事实源。第一版不预建未经批准的模块。

## Skill source and deployment model

四个位置必须分开：

1. **Source Repository：** 开发、评审、验证和保存历史的唯一仓库。
2. **Source Skill Package：** 仓库内自包含的 Skill 目录，是安装内容的唯一手工维护源。
3. **Installed Copy：** 从源包部署到用户级 Skills 的副本，不作为手工编辑或规则演进来源。
4. **Target Project：** Skill 实际协助的项目，提供自己的目标、规则、状态和证据。

源 Skill 包必须携带运行所需的模板和资源，不得依赖源仓库的 `docs/`、根目录资产或固定绝对路径。目标项目无需克隆 Source Repository，也不要求采用 Agent Project System 的目录结构。安装和更新必须从源包进行并验证完整性，不得静默覆盖安装位置中的未知修改。项目级同名 Skill 与用户级 Skill 不得无意并存；发现同名来源时必须显式处理版本和选择，不能假设静默覆盖。

## User communication and decision gates

与用户沟通使用白话并尽量减少打扰。只有目标方向、成本付费、账号权限、隐私数据、文件公开上传、不可逆操作、重大安全风险或必须接受降级时请求决定。所有决策请求必须提供三个白话选项和一个明确推荐。

## Safety and information exchange

- 不读取 Cookie、Token、密钥或平台账号凭据，不扫描私人文件。
- 未经授权不上传文件、安装依赖、改变远端或公开内容。
- 浏览器端与 IDE 端以文字摘要、关键 Diff、命令退出码和必要测试输出交换信息，不依赖自动文件上传。
