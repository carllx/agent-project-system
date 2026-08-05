# IDE Agent 硬规则

本仓库是通用 Agent Project System。IDE Agent 负责在项目目录内执行、验证并报告本地事实；任何任务开始前必须先确认当前唯一 Work Item。

## 会话启动顺序

1. `AGENTS.md`
2. `README.md`
3. `docs/index.md`
4. `docs/current.md`
5. 根据 Index 的 `Read when` 读取适用的 Spec、ADR、Skill 或模板

## 项目目录

- `docs/`：登记表、当前状态、Spec 与 ADR 等权威知识。
- `skills/`：已登记的正式运行模块。
- `assets/packets/`：可复用模板资产，不存放实际运行实例。
- `scripts/`：项目检查工具；当前入口是 `scripts/check_docs.py`。

## 决策与规则权威

由高到低：

1. 用户当前明确决定和授权
2. `AGENTS.md`
3. 已登记且适用的 ADR / Spec
4. 当前 Work Item 的目标和验收标准
5. Skill 的操作步骤

所有决定都必须处于安全、隐私、权限和不可逆操作边界内。Skill 或状态记录不能推翻用户当前决定。

## 事实与证据权威

由高到低：

1. 真实文件、命令输出、测试结果和 Git Diff
2. `docs/current.md` 中已记录的事实
3. Agent 摘要
4. 外部推测和未验证建议

规则不能伪造事实；事实也不能擅自覆盖用户决定或安全边界。外部判断与本地证据冲突时，以本地证据纠偏并如实报告。

## 执行边界

- 第一版任何时刻只允许一个 Active Work Item；先读 `docs/current.md`。
- 只操作本项目目录及用户为当前任务明确提供的文件；不得扫描私人文件。
- 不得尝试读取 Cookie、Token、密钥或平台账号凭据。
- 未经明确授权，不得上传、公开、付费、安装依赖、改变账号权限或执行不可逆操作。
- 不得默认执行 `git add`、`git stash`、commit、push 或重写历史。
- 临时 Packet、Handoff、调查草稿、Session Summary 和日期状态副本默认不得提交。
- 运行模块与模板资产必须登记在 `docs/index.md`。

## 文档创建闸门

新增长期 Markdown 前必须同时满足：

1. 路径符合 `docs/specs/`、`docs/adr/`、`docs/references/`、`skills/*/SKILL.md` 或 `assets/packets/` 的允许类型；
2. 内容不是现有权威文档的重复事实源；
3. 已登记到 `docs/index.md`，写明 Authority、Read when、Status 和 Last verified；
4. 通过 `python scripts/check_docs.py`。

根目录只允许 `AGENTS.md`、`README.md` 和可选的 `CLAUDE.md`。工具适配文件只能引用权威文档，不得复制规则。无法满足闸门时暂停并请求用户决定。

## 验证命令

本项目当前没有构建步骤。修改后至少运行：

```bash
python scripts/check_docs.py
git diff --check
git status --short
```

需要说明变更时使用 `git diff --stat` 和必要的关键 Diff，不得虚构验证结果。

## 用户决策闸口

仅在目标或产品方向变化、成本或付费、账号和权限、隐私和私人数据、文件公开或上传、删除覆盖等不可逆操作、重大安全风险，或当前目标无法实现而需降级时暂停。提问必须给出三个白话选项和一个明确推荐。
