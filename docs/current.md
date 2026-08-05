# Current Project State

## Project identity

- **Name:** Agent Project System
- **Repository root:** `E:\PROJECTS\agent-project-system`
- **Remote:** `https://github.com/carllx/agent-project-system.git`
- **Branch:** `main`

## Active Work Item

- **Name:** 在源仓库实现 OpenCLI 循环并重新发布实验包
- **Work Item state:** `ACHIEVED`
- **Baseline commit:** `94741a489845155fe623db08b92fe3201719f0c1`
- **Current objective:** 审查被污染的实验副本，在唯一源仓库实现角色分离、OpenCLI 真实循环契约、Conversation 身份和 Human-in-the-loop，再以受控整包替换方式重新同步实验包。

## Acceptance criteria

- 污染实验包的变更、哈希、可采用设计和不可靠假设已由只读证据区分。
- 源 Skill 明确 Builder IDE Agent、IDE-side Loop Driver 和真实 Browser RR Lead。
- 源包包含五份唯一资产，版本为 `0.2.0`，且不运行时依赖源仓库。
- Skill 包含完整 Loop 状态机、Conversation 身份、停止状态、HITL 暂停和恢复。
- OpenCLI 帮助已核验的语法与尚未完成的 Browser E2E 语义明确分开。
- 包检查、文档检查、Skill Creator 校验和 Git whitespace 检查通过。
- 验证后创建一个授权的本地 Commit，不 push。
- 新 Commit 后完整替换实验包，并证明源/实验哈希相同、无额外文件、业务 fixture 未变化。

## Completed

- 已固定自包含源包基线 `94741a4`。
- 已只读确认实验 Agent 只修改了实验包 `SKILL.md` 并新增 `assets/rr-lead-init.md`；其余六个原文件与源基线一致。
- 已记录污染包和业务 fixture 的聚合哈希。
- 已从本机 OpenCLI `1.8.6` 帮助确认 ChatGPT adapter 的命令名称、参数和声明输出字段，未运行 Browser 传输。
- 已在源包重新实现角色分离、循环状态机、Conversation 身份和 HITL，并升级为 `0.2.0`。
- 已增加 Browser RR Lead 初始化资产、五资产检查和四层测试规范。
- 已通过文档、源包、Skill frontmatter 和 Git whitespace 静态验证；传输、循环与 HITL E2E 明确保留到下一阶段。

## In progress

- None.

## Blockers

- None.

## Decisions pending

- None.

## Next action

- 以新源 Commit 完整替换实验包，随后运行 Transport Smoke Test。

## Files to read

- `AGENTS.md`
- `README.md`
- `docs/index.md`
- `docs/specs/research-review-loop.md`
- `docs/adr/0002-self-contained-user-level-rr-lead-skill.md`
- `skills/research-review-lead/SKILL.md`
- `skills/research-review-lead/assets/rr-lead-init.md`

## Last validation

- **Command:** `python scripts/check_docs.py`
- **Result:** Passed; all long-term Markdown is registered and allowed.
- **Command:** `python scripts/check_skill_package.py`
- **Result:** Passed; version, five unique assets, portability and loop-contract markers are valid.
- **Command:** Skill Creator `quick_validate.py skills/research-review-lead`
- **Result:** Passed; Skill frontmatter is valid.
- **Command:** `git diff --check`
- **Result:** Passed.
- **Scope:** Static source-package validation only; OpenCLI transport, loop and HITL E2E remain unverified.
- **Last verified:** 2026-08-05
