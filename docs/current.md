# Current Project State

## Project identity

- **Name:** Agent Project System
- **Repository root:** `E:\PROJECTS\agent-project-system`
- **Remote:** `https://github.com/carllx/agent-project-system.git`
- **Branch:** `main`

## Active Work Item

- **Name:** 核验迁移落点并重构 RR Lead 自包含 Skill 包
- **Work Item state:** `ACHIEVED`
- **Baseline commit:** `4e3b61bb76628d5b4d1bc69ff0fe4c56aa76de05`
- **Current objective:** 确认信息架构迁移的真实 Git 落点，并将 `research-review-lead` 重构为可部署、跨项目运行且不依赖源仓库的 Codex 源 Skill 包。

## Acceptance criteria

- 信息架构迁移已确认安全存在于 Git 历史，且工作区来源清楚。
- 源 Skill 包包含 `SKILL.md`、`VERSION` 和四个唯一模板资产。
- Skill 不依赖源仓库 `docs/`、根目录 Packet 或目标项目固定结构。
- Full Governance Mode 与 Compatibility Mode、通用证据模型和双角色 Handoff 已定义。
- README、治理 Spec、RR Loop Spec、Index 和 ADR 与源包模型一致。
- 文档检查、Skill 包检查和 Git whitespace 检查通过。
- 不安装 Skill，不修改 Codex 配置，不 commit、不 push。

## Completed

- 已确认迁移前基线 `ccc8227` 是当前 HEAD 的祖先。
- 已确认信息架构迁移提交为 `4e3b61b`，其包含新 Index、Current、Specs、ADR 和检查器，并移除了旧 Charter、Architecture、workflows、templates 与 state 路径。
- 已确认本 Work Item 开始时 HEAD 与远端 `main` 一致，工作区和暂存区干净且无 stash。
- 已将 Packet 模板迁入 RR Lead 源 Skill 包，并将 Change Packet 泛化为 Evidence Packet。
- 已加入源包版本、两种运行模式、通用证据模型和自包含路径。
- 已更新 README、治理 Specs、Index 和 ADR，并通过文档、源包、Skill frontmatter 与 Git whitespace 检查。

## In progress

- None.

## Blockers

- None.

## Decisions pending

- None.

## Next action

- 用户审查当前未提交工作区；后续另开 Work Item 设计安装器和受控安装 dry-run。

## Files to read

- `AGENTS.md`
- `README.md`
- `docs/index.md`
- `docs/specs/system-governance.md`
- `docs/specs/research-review-loop.md`
- `docs/adr/0002-self-contained-user-level-rr-lead-skill.md`
- `skills/research-review-lead/SKILL.md`

## Last validation

- **Command:** `python scripts/check_docs.py`
- **Result:** Passed; all long-term Markdown is registered and allowed.
- **Command:** `python scripts/check_skill_package.py`
- **Result:** Passed; entry, version, four unique assets and portability rules are valid.
- **Command:** Skill Creator `quick_validate.py skills/research-review-lead`
- **Result:** Passed; Skill frontmatter is valid.
- **Command:** `git diff --check`
- **Result:** Passed.
- **Last verified:** 2026-08-05
