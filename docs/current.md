# Current Project State

## Project identity

- **Name:** Agent Project System
- **Repository root:** `E:\PROJECTS\agent-project-system`
- **Remote:** `https://github.com/carllx/agent-project-system.git`
- **Branch:** `main`

## Active Work Item

- **ID:** `TRANSPORT-A2P2-RECOVERY-026`
- **Name:** 分析 A2.2 DELIVERY_UNKNOWN 与外层 schedule 漏报
- **Work Item state:** `ACHIEVED`
- **Baseline commit:** `7d40e1f39da3a23c50dcefbe5cba207a2b1198fd`
- **Current objective:** 确认 `TRANSPORT-A2P2-025` 的发送与恢复边界，补齐 NEW 模式 post-send history 恢复，并修正外层 Agent schedule 报告语义。

## Acceptance criteria

- 只读取 `TRANSPORT-A2P2-025` 指定七个证据文件，不运行真实 Browser、不发送消息、不修改历史 Runtime。
- 正确分类 ask、发送后 status 与 detail 实际目标，不根据 Browser 外观猜测。
- NEW 模式执行有限 pre-send baseline、单次发送、post-send status、单次 post-send history、baseline diff 与最多一次 exact-ID detail。
- 保留 `MISROUTED_DELIVERY`、`DELIVERY_UNKNOWN` 和相同 Message ID 永久禁止重发语义。
- 区分 Wrapper、Agent 与 Total schedule 计数；无法观察外层轨迹时明确 `UNAVAILABLE`，报告冲突必须失败。
- 版本升至 `0.4.7`，纯本地 Transport、治理、包和 Skill Creator 校验通过。
- 本地 Commit（不 push），Lab 整包同步且源/Lab 字节一致，指定 Runtime 保持不变。

## Confirmed facts

- `raw/04-ask.json` 的 `returncode=0`、`timed_out=false`、stderr 为空；flat YAML stdout 明确报告 Conversation ID `6a734bbd-df5c-83ea-95e8-06e6967be6df`、同 ID URL 与 response，分类为 `A. ASK_CONFIRMED_DELIVERY_WITH_ID`。
- `raw/05-status-after-send.json` 的 `returncode=0`，URL 为同一新 `/c/6a734bbd-df5c-83ea-95e8-06e6967be6df`，页面模式为 Conversation；没有停留 `/new` 或返回根页面。
- 旧 Wrapper 从发送后 status 取得该新 ID，并用 `detail <id>` 检查它；`raw/06-detail.json` 只含精确 Work Item ID，不含 Message ID，因此旧 exact-two-marker 检查未命中。
- 旧 `result_rows` 只解析 JSON，漏掉真实 ask flat YAML 身份；旧恢复在 status 已有 ID 时跳过 post-send history。
- 历史实验可见 Agent 工具轨迹至少有两次 schedule，而 Runtime 的 `schedule_call_count=0` 只能代表 Wrapper 内部；在本轮允许的证据范围内无法可靠重数完整 Agent 轨迹，因此历史报告必须标记 `AGENT_TOOL_TRACE_VERIFICATION=UNAVAILABLE`、协议违规且实验验收不能为 `MET`。

## Completed

- ask 身份解析支持 JSON 与严格的首个 flat YAML record，并校验 ID、精确 ChatGPT `/c/<id>` URL 和二者一致性；正文伪造、block scalar、非 ChatGPT URL 与身份冲突均保守拒绝。
- NEW 恢复固定执行一次 post-send status 与一次有限 history refresh，排除发送前 ID，只对 ask 身份、当前 status 或唯一新增候选中的最强目标执行最多一次 detail；多新增候选保持未知。
- detail 只有在底层命令真实调用后才计数；EXISTING 模式合法恢复不再被误判为 misroute。
- Work Item ID 与 Message ID 使用独立 Header 整行精确匹配，拒绝前缀碰撞。
- 报告字段拆分为 `WRAPPER_SCHEDULE_CALL_COUNT`、`AGENT_SCHEDULE_CALL_COUNT`、`TOTAL_SCHEDULE_CALL_COUNT`、`AGENT_TOOL_TRACE_VERIFICATION` 与 `AGENT_BOUND_RESULT_RETRIEVAL_COUNT`；缺字段、伪零、无效枚举、违规后 PASS/MET 和 `DELIVERY_UNKNOWN` 允许重发均使 `REPORT_VALIDATION_FAILED=true`。
- 独立审查 Agent 最终结论为 `PASS`，先后发现的 EXISTING 误判、YAML 正文伪造、detail 虚计数、报告默认伪零和 ID 前缀碰撞均已修复并回归。
- 72 项纯本地 Transport 测试、文档治理、0.4.7 包检查和 `git diff --check` 已通过。
- 权威源包已逐文件同步到 `E:\PROJECTS\rr-lead-skill-lab\.agents\skills\research-review-lead`；源/Lab 各 8 文件、版本均为 0.4.7、字节差异为零，规范包哈希均为 `f5b87edd3336622a4df9fe327da7b93d881b76e1da375a2da52353a5c0ae5d90`。
- 指定 `TRANSPORT-A2P2-025` 七个文件的同步前后 SHA-256 差异为零；未读取其他 Runtime。

## Blockers

- None.

## Decisions pending

- None.

## Next action

- 如需重新验收 A2.2，使用全新的 Work Item ID、Message ID 与 Runtime；禁止重发 `MSG-TRANSPORT-A2P2-025-01`。实验 Agent 必须从其可见工具轨迹填写 Agent schedule 与绑定结果读取计数，任何 schedule 调用都使协议违规且实验验收不能为 `MET`。

## Files to read

- `AGENTS.md`
- `README.md`
- `docs/index.md`
- `docs/specs/research-review-loop.md`
- `skills/research-review-lead/SKILL.md`
- `skills/research-review-lead/scripts/opencli_transport.py`
- `scripts/test_opencli_transport.py`

## Last validation

- **Command:** `python scripts/test_opencli_transport.py`
- **Result:** Passed 72 pure-local scenarios, including the required A2.2 recovery, exact-identifier, schedule-reporting, deduplication, A2.1, existing-send and prior send regressions.
- **Command:** `python scripts/check_docs.py`
- **Result:** Passed; 14 registered Markdown files.
- **Command:** `python scripts/check_skill_package.py`
- **Result:** Passed for version `0.4.7` and the exact eight-file package.
- **Command:** Skill Creator `quick_validate.py` for source and Lab packages
- **Result:** Passed for both packages.
- **Command:** `git diff --check`
- **Result:** Passed; only Git line-ending conversion warnings were emitted.
- **Command:** source/Lab relative-path manifest, per-file SHA-256 comparison, and canonical package hash
- **Result:** Both contain 8 files; path and byte diff counts are zero; both canonical hashes are `f5b87edd3336622a4df9fe327da7b93d881b76e1da375a2da52353a5c0ae5d90`.
- **Command:** authorized `TRANSPORT-A2P2-025` seven-file SHA-256 comparison before/after sync
- **Result:** All seven authorized Runtime files are unchanged; content diff count is zero.
- **Scope:** 只使用指定 Runtime、脱敏纯本地 fake OpenCLI 与静态检查；未运行真实 OpenCLI、Browser 实验或发送消息。
- **Last verified:** 2026-08-05
