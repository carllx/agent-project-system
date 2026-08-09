# Current Project State

## Project identity

- **Name:** Agent Project System
- **North star:** 建立一套与具体 IDE 和 Transport 解耦的 **Agent Collaboration Framework**，使 Browser Lead 与 IDE Agent 能通过可定义、可观察、可恢复、可审查、可测试的协议形成长期工作闭环。见 `docs/adr/0003-agent-collaboration-framework.md`。
- **Repository root:** `E:\PROJECTS\agent-project-system`
- **Remote:** `https://github.com/carllx/agent-project-system.git`
- **Branch:** `main`
- **HEAD:** `1d2c44b`（`feat: deterministic bootstrap and manual relay for RR Lead (0.4.15)`）
- **Source Skill VERSION:** `0.4.15`。
- **OBSERVED_LOCAL_INSTALL_PATH:** `C:\Users\carll\.codex\skills\research-review-lead`；目录存在，VERSION `0.4.15`，九个文件与源包逐文件 SHA-256 一致。
- **HISTORICAL_DESIGN_TARGET:** `$HOME/.agents/skills/research-review-lead`（ADR-0002）；本机当前不存在。
- **CANONICAL_DEPLOYMENT_PATH:** `UNVERIFIED`。仓库没有安装脚本；项目历史记录了 `.codex\skills` 的本机安装结果，但不能证明它是所有平台通用的 canonical Codex 用户级 Skill 路径。

## 系统目标

Agent Project System 不是单独的 RR Lead Skill，也不是 OpenCLI Transport，而是一套与具体 IDE 和 Transport 解耦的 Agent Collaboration Framework：

```text
Agent Project System
→ Agent Collaboration Framework
→ Browser Lead / IDE Agent Collaboration Protocol
→ Runtime / Orchestration
→ Transport / IDE Adapters
```

- **Browser Lead：** 负责规划、架构、Review 与被授权范围内的技术判断。
- **用户：** 保留目标、范围、权限、风险、成本和重要产品方向的最终决定权。
- **参考 IDE 顺序：** Antigravity 为第一参考 IDE；Codex 后续用于跨 IDE 通用性验证。
- **OpenCLI：** 只是 Transport Adapter，不等于整个系统。
- **rr-lead-skill-lab：** 独立实验环境，不是正式产品源码仓库。

## 当前模块

- `skills/research-review-lead/`：已登记的正式运行模块（RR Lead Loop + 确定性 bootstrap + manual-export fallback），VERSION `0.4.15`。
- OpenCLI Transport Adapter：`skills/research-review-lead/scripts/opencli_transport.py` 中的 Transport 层实现，仅作为框架的适配器。

## Completed Work Item

- **ID:** `BOOTSTRAP-MANUAL-RELAY-001`
- **Name:** 确定性 Browser Bootstrap 与 Manual Relay fallback
- **Review decision:** `PASS_WITH_DEBT`
- **Work Item state:** `ACHIEVED`
- **Skill version:** `0.4.14` → `0.4.15`
- **安装状态（本地事实）：** `OBSERVED_LOCAL_INSTALL_PATH` 存在且与源包一致；不据此声明 canonical 部署路径。

### Acceptance 状态

- **MET（本 Work Item 已完成）：**
  - `SOURCE_PACKAGE_TESTED=true`
  - `DETERMINISTIC_BOOTSTRAP_IMPLEMENTED=true`（本地全绿；真实 Browser 未验）
  - `MANUAL_RELAY_IMPLEMENTED=true`（本地全绿）
  - `OBSERVED_LOCAL_INSTALLATION=true`（本机 `.codex\skills` 副本 VERSION `0.4.15`，九文件清单与源包逐项匹配；不等于 canonical path 已证明）
- **TRANSFERRED_TO_ACF_SYSTEM_TEST（经用户批准转移）：**
  - `DISCOVERY`
  - `0.4.15 RR_REVIEW live envelope`
  - `same-Conversation two-round integration`
  - `final live collaboration smoke`
- **旧 Transport 历史（不再重复实验）：**
  - `LIVE_TRANSPORT_DELIVERY_VERIFIED=true`（已由 `FIRST-USE-LOOP-001` 与过往 Live ACK 证明“OpenCLI 能收发”，不再单独重复）。

### 用户批准的验证策略调整（2026-08-08）

不再单独为了证明 OpenCLI 能收发而重复实验。剩余 Live Gate（Discovery、RR_LEAD_PROTOCOL_VERIFIED、TWO_ROUND_SMOKE_VERIFIED、LIVE_SMOKE_TEST_PASSED）合并到后续第一轮真实 Agent Collaboration System Test 中完成，验证完整闭环：

```text
IDE Agent → Browser Review → Decision → IDE Execution → Evidence → Browser Result Review
```

这些责任没有被删除，也没有被伪造为 PASS；经用户批准，它们已从 `BOOTSTRAP-MANUAL-RELAY-001` 转移到后续 ACF System Test 的验收范围。转移后，本 Work Item 不再存在属于自身的未满足 Acceptance Criterion，因此以 `PASS_WITH_DEBT / ACHIEVED` 收口。

## 已证明能力

- 真实 RR Loop 两轮闭环成功：`FIRST-USE-LOOP-001`，`FIRST_USABLE_VERSION: 0.4.14`，最终 Browser 判定 `PASS / ACHIEVED`；无重发、无用户复制、无 push。
- 确定性 bootstrap：Wrapper 读取 init+context 文件，去除 UTF-8 BOM、统一换行、发送前拒绝非法 UTF-8/孤立 surrogate，按固定顺序与唯一边界组装；manifest 含字节数/字符数/行数/SHA-256；复用现有 send + bounded recover，同一 Message ID 只发一次。
- manual-export / `MANUAL_RELAY_REQUIRED`：不调用 OpenCLI、不建 Conversation、不增 send count、Work Item 保持 `IN_PROGRESS`；导出 hash 与准备发送正文一致。
- 严格结构化 RR_REVIEW 解析、身份绑定、同 Message ID 禁重发；纯本地 Transport 回归 169 项全部通过，checker unittest 14/14。
- `LIVE_TRANSPORT_DELIVERY_VERIFIED=true`（旧历史证明 Transport 能收发；不再重复实验）。

## 已转移的系统级验收

- Discovery、0.4.15 RR_REVIEW live envelope、same-Conversation two-round integration 与 final live collaboration smoke 由后续 ACF System Test 验收。
- 在该系统测试完成前，不声明这些 transferred criteria 为 PASS。

## Blocker / Debt

- **Blocker：** 无。
- **Debt（不阻止旧 Work Item 完成）：** 后续证据应区分 `PROBE_CONVERSATION_ID` 与 `RR_LOOP_CONVERSATION_ID`，避免把独立探针 Conversation 误写为当前 Loop Conversation。

## 下一 Work Item 候选

- `NEXT_WORK_ITEM_CANDIDATE: ACF-PROTOCOL-001`
- 候选项尚未启动，不是 Active Work Item。

## Files to read

- `AGENTS.md`
- `README.md`
- `docs/index.md`
- `docs/adr/0003-agent-collaboration-framework.md`

## Last validation

- **Command:** `python scripts/check_docs.py`
- **Result:** Passed；15 Markdown files registered；AGENTS.md 78/100；无禁用路径或垃圾副本。
- **Command:** `git diff --check`
- **Result:** Passed（exit 0；只有工作树换行转换提示，无 whitespace error）。
- **Command:** `git status --short`
- **Result:** 仅 README、current、index、system-governance 与 ADR-0003 五个授权文件有变更；ADR-0002 历史正文未修改。
- **Command:** `git diff --stat`
- **Result:** Passed；默认 stat 覆盖四个已跟踪治理文件；未跟踪且已登记的 ADR-0003 在暂存后计入 commit stat。
- **Last verified:** 2026-08-09
