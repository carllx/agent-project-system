# Antigravity Completion-Gate Adapter v0.1

## Authority and purpose

本 Spec 是 Antigravity Completion-Gate Adapter 当前行为、状态映射、最小 Contract、bounded continuation 与失败语义的唯一权威。架构理由见 `docs/adr/0004-antigravity-completion-gate-adapter.md`；通用 Review 与 Completion Authority 语义仍只由 `docs/specs/agent-collaboration-protocol.md` 定义。

本 Adapter 把 ACF Workflow State 映射为 Antigravity Stop lifecycle 上的 `ALLOW_STOP`、`CONTINUE_BOUNDED` 或 `BLOCK_AND_ESCALATE`。它防止 Execution Agent 在仍有可执行必要动作时因一次自然停止而丢失工作，但不把 execution 持续运行等同于 Work Item 完成。

```text
ACF Protocol
→ Workflow State
→ Completion-Gate Policy
→ Antigravity Adapter
→ Stop Hook
```

## Responsibility boundaries

- **ACF Protocol:** 定义 Review Trigger、Request/Decision Contract、权限绑定与完成不变量；本 Adapter 不修改 `ACF-0.1`。
- **Workflow State:** 由 Orchestration 按权威协议事件维护；Hook 不自行推断或改写 Review Decision。
- **Completion-Gate Policy:** 根据已验证的 Workflow State、必须动作和 continuation budget 选择 Adapter Outcome。
- **Antigravity Adapter:** 把通用 Outcome 转换为 Antigravity Stop Hook 支持的返回行为，并记录最小审计事实。
- **Stop Hook:** 只读取输入、调用 Policy、返回 `allow` 或 `decision=continue`；它不是 Completion Authority，也不负责 Review。
- **Transport:** 只负责消息传递、身份绑定与恢复。OpenCLI 的 `DELIVERY_UNKNOWN / BLOCKED` 不改变 Completion-Gate 语义，也不阻塞本 Adapter 的产品化。

本 Adapter 不解决 Browser Review 传输、第三方模型是否真实发生 premature stop、Hook 安装位置选择、跨 IDE 通用 Hook schema 或 ACF 产品化的其他部分。

## Workflow State to Stop behavior

| Workflow State | 条件 | Adapter Outcome | Work Item completion |
| --- | --- | --- | --- |
| `EXECUTING` | 存在当前授权范围内尚未完成且可执行的必要动作，预算可用 | `CONTINUE_BOUNDED` | 不变，仍未完成 |
| `EXECUTING` | 没有可安全执行的当前必要动作 | `ALLOW_STOP` | 不变，仍未完成 |
| `REVISION_REQUIRED` | Browser `REQUIRED_ACTIONS` 尚未完成，动作可执行，预算可用 | `CONTINUE_BOUNDED` | 不变，仍未完成 |
| `REVISION_REQUIRED` | 动作缺失、不可执行或预算耗尽 | `BLOCK_AND_ESCALATE` | 不变，仍未完成 |
| `INTERMEDIATE_REVIEW_PENDING` | 正在等待 Browser Decision | `ALLOW_STOP` | 不变，仍未完成 |
| `FINAL_REVIEW_PENDING` | 正在等待 Browser Final Decision | `ALLOW_STOP` | 不变，仍未完成 |
| `WAITING_FOR_USER` | 正在等待用户本人明确决定 | `ALLOW_STOP` | 不变，仍未完成 |
| `COMPLETED` | Completion invariant 已重新验证 | `ALLOW_STOP` | 已完成 |
| 未知、矛盾或无法验证 | 任意 | `BLOCK_AND_ESCALATE` | 禁止进入或保持 `COMPLETED` |

`没有 Final APPROVE` 不等于 `永远 continue`。Review Pending 与 Waiting for User 必须允许当前 execution idle/Stop；否则 Hook 会把合法等待误变成无限执行循环。`ALLOW_STOP` 只允许当前 execution 终止，不授予 Work Item 完成状态。

## Completion invariant

Adapter 只在 Orchestration 已按 `ACF-0.1` 验证下列条件后接受 `WORKFLOW_STATE=COMPLETED`：

1. `PROTOCOL_VERSION` 匹配当前协议；
2. `WORK_ITEM_ID` 匹配当前 Work Item；
3. `IN_REPLY_TO_REVIEW_REQUEST_ID` 匹配当前 Pending Final Review Request；
4. `REVIEW_KIND=FINAL`；
5. `REVIEW_DECISION=APPROVE`；
6. 所有 agreed Acceptance Criteria 均为 `MET`；
7. 没有 unresolved User Decision；
8. Final Review Request 之后没有足以使批准 stale 的实质性修改。

这些条件必须由 Decision 原始字段和当前工作状态推导，不能只信任调用方提供的单个 `FINAL_APPROVAL_VALID=true` 布尔值。任一条件为 false 或 `UNVERIFIED` 时，不得进入 `COMPLETED`。Hook 不得自行批准、补齐或伪造这些事实。

## Adapter Contract

### Input

```text
ADAPTER_VERSION
PROTOCOL_VERSION
WORK_ITEM_ID
WORKFLOW_STATE
PENDING_REVIEW_REQUEST:
  REVIEW_REQUEST_ID
  REVIEW_KIND
AUTHORITATIVE_REVIEW_DECISION:
  PROTOCOL_VERSION
  WORK_ITEM_ID
  IN_REPLY_TO_REVIEW_REQUEST_ID
  REVIEW_KIND
  REVIEW_DECISION
  ACCEPTANCE_STATUS
  USER_DECISION_REQUIRED
  REVIEWED_STATE_CURRENT: true / false / UNVERIFIED
UNRESOLVED_USER_DECISION: true / false / UNVERIFIED
CURRENT_REQUIRED_ACTION:
  ACTION_ID
  DESCRIPTION
  STATUS: PENDING / COMPLETED / BLOCKED / UNVERIFIED
CONTINUATION_STATE:
  ACTION_ID
  CONTINUATION_COUNT
  CONTINUATION_BUDGET
  CONTINUE_REASON
STOP_RUNTIME_METADATA:
  conversationId
  workspacePaths
  executionNum
  terminationReason
  fullyIdle
```

与当前状态无关的复合字段可以显式为 `NONE`，但不得省略到无法区分 `NONE` 与未知。Antigravity 的 runtime metadata 只属于 Adapter 输入，不进入通用 ACF Protocol schema。

### Runtime routing configuration

Global Hook 通过 `--config <path>` 显式加载动态 route config。配置必须声明受支持的 `adapter_version`；每条 route 至少包含唯一 `route_id`、精确 `workspace_path`、`work_item_id` 和 `state_path`。可选 `conversation_id` 用于进一步收窄目标，可选 `evidence_path` 保存结构化决策记录。路径和 identity 由部署者在目标环境配置，产品源码不得内置具体 workspace、Conversation、实验 ID 或临时 state 路径。多条 route 同时匹配与零匹配都返回 Antigravity `ignore`，避免全局 Hook 污染无关 Agent；route 与 state 的 Work Item 不匹配时必须 `BLOCK_AND_ESCALATE`。

Windows 部署命令必须使用已验证 Python executable 与本仓库 `stop_hook.py` 的绝对路径，并使用大小写准确的 `Stop` 事件键。Global 与 workspace-local 的最终部署选择仍为后续 Decision；本 Work Item 不写入用户级 `hooks.json`。

### Output

```text
ADAPTER_OUTCOME: ALLOW_STOP / CONTINUE_BOUNDED / BLOCK_AND_ESCALATE
REASON
WORK_ITEM_COMPLETED: true / false
CONTINUATION_STATE
EVIDENCE_RECORD
```

- `ALLOW_STOP`：允许当前 execution 正常终止；只有 Completion invariant 已满足时 `WORK_ITEM_COMPLETED=true`。
- `CONTINUE_BOUNDED`：Antigravity Adapter 返回 `decision=continue`，携带当前必要动作与原因，并原子增加该动作的 continuation count。
- `BLOCK_AND_ESCALATE`：不再自动 continue，保持 `WORK_ITEM_COMPLETED=false`，记录 Blocker 与人工 Review 所需证据，然后允许 execution 停止。Orchestration 可在 Transport 可用时提交 `BLOCKER` Intermediate Review；Transport 不可用时保留可人工转交的 Review requirement，但 Adapter 本身不发送消息。

## Bounded continuation policy

v0.1 对同一 `ACTION_ID` 的默认 `CONTINUATION_BUDGET=1`。一次 Stop lifecycle 最多消费一次；同一动作的重复 Stop 不得因重启 Hook、重读文件或 `executionNum` 变化而重置预算。

预算只在以下事件之一发生时重置：

- Browser 返回新的权威 `REQUIRED_ACTIONS`，形成新的 `ACTION_ID`；
- 当前动作产生可验证的实质进展，并由 Orchestration 明确建立后继 `ACTION_ID`；
- 用户明确决定更新 Goal、Scope 或 Constraints 后，Orchestration 建立新的必要动作。

普通重试、无证据的“仍在处理”、自然 Stop 或 Adapter 重启都不是重置条件。预算耗尽、动作不可执行、动作身份缺失或 continuation state 无法验证时，Outcome 必须是 `BLOCK_AND_ESCALATE`，禁止继续唤醒。

## Evidence requirements

每次决策至少记录：Adapter/Protocol version、Work Item、Workflow State、Stop runtime metadata、当前动作、消费前后 budget/count、Outcome、Reason，以及用于判断 Final Approval 是否权威且仍有效的字段。记录必须足以解释为何允许 Stop、为何 continue，或为何停止自动恢复；不得保存完整聊天来替代结构化事实。

### Lab evidence provenance

- **Bundle experiment label:** `ACF-AG-HOOK-GLOBAL-ANCHORED-005`。
  - **Observed evidence directory:** `ACF-AG-HOOK-GLOBAL-ANCHORED-V260-005`；Bundle 标签与本机目录名不一致，本 Spec 保留两者而不伪造归一化。
  - **Environment:** Antigravity 2.6.0 Global Stop Hook。
  - **Proven:** Stop stdin 字段被真实观察；`decision=continue` 后同一 Conversation 从 `executionNum=0` 自动恢复至 `executionNum=1`，并随后正常 Stop。
  - **Path:** `E:\PROJECTS\rr-lead-skill-lab\experiments\ACF-AG-HOOK-GLOBAL-ANCHORED-V260-005\`。
- **Experiment:** `ACF-AG-COMPLETION-GATE-SYSTEM-001`
  - **Product baseline:** `af5d84afe314efaf9ee7bd2ad6080a032026a00d`；`PROTOCOL_VERSION=ACF-0.1`。
  - **Proven:** `REVISION_REQUIRED` 且 Final Approval 无效时，Stop lifecycle 可执行 bounded continue，使 Agent 恢复并继续 Browser `REQUIRED_ACTIONS`；Review Pending 与 Waiting for User 应允许 idle 的映射由该实验 Amendment 固化。
  - **Path:** `E:\PROJECTS\rr-lead-skill-lab\experiments\ACF-AG-COMPLETION-GATE-SYSTEM-001\`。

这些目录是独立 Lab 的 point-in-time Evidence Source，不是本仓库产品实现，且不证明下列行为：真实 DeepSeek premature-stop occurrence 的恢复、workspace-local Hook 的最终部署形式、stale approval enforcement。

### Reference implementation findings

Productization Evidence Bundle `C:\Users\carll\.gemini\antigravity\brain\aa315c66-5d82-44f8-8ea5-847f5b1be277\acf_ag_adapter_001_handoff.md` 及其指向的成功 Probe/Gate 脚本仅作为 `REFERENCE IMPLEMENTATION + EVIDENCE`。正式 Completion-Gate Policy 位于 `runtime/completion_gate.py`，Antigravity translation 位于 `adapters/antigravity/stop_hook.py`；两者重新实现 Contract，不复制 Prototype。

已提取并保留的机制与约束：

- Stop Hook 从 stdin 读取 JSON，并只把 Adapter Outcome 翻译为 Antigravity 的 `stop / continue / ignore`；`decision=continue` 不进入 ACF Core 或 Protocol。
- Global Hook 会作用于所有 Antigravity Agent，必须先用规范化后的精确 workspace 路径和可选 Conversation identity 做唯一 route 匹配；未匹配或多重匹配返回 `ignore`，禁止 substring routing leakage。
- Windows Antigravity child process 使用裸 `python` 曾出现 exit 9009；部署配置必须使用经验证的 Python executable 绝对路径。该要求属于 Antigravity 部署，不是 ACF Contract 字段。
- `hooks.json` 的事件键必须写作 `Stop`。当前成功配置位于 Global Hook；workspace-local discovery 仍为 `UNVERIFIED`。
- Lab 的扁平 `gate_state.json`、`HAS_CONTINUED_THIS_REVISION`、硬编码 workspace/conversation、实验路径与 Lab 命名均不进入正式实现。正式实现使用动态 route config、按 `ACTION_ID` 绑定的 continuation state，并从完整 Review 字段推导 Final Approval 权威性。

## Failure and fallback semantics

- **状态或证据缺失/矛盾：** `BLOCK_AND_ESCALATE`；不得把未知降级为 `COMPLETED`。
- **continuation budget 耗尽：** `BLOCK_AND_ESCALATE`；不得无限返回 `decision=continue`。
- **Review/用户等待：** `ALLOW_STOP` 且 `WORK_ITEM_COMPLETED=false`；等待本身不是失败。
- **Hook 未触发或运行失败：** Adapter enforcement 为 `UNVERIFIED`。execution 可能终止，但系统不得因此声明 Work Item 完成；后续恢复时必须重新校验 Workflow State 和 Completion invariant。
- **Transport 不可用：** 不重试或伪造 Review Decision；记录人工转交需求并允许 execution 停止。Completion Gate 与 Transport 故障保持解耦。

## Deferred validations

1. `THIRD_PARTY_PREMATURE_STOP`：真实 DeepSeek 等第三方模型异常停止是否进入同一 Stop lifecycle 并可恢复。
2. `OPENCLI_TRANSPORT_RECOVERY`：`DELIVERY_UNKNOWN / BLOCKED` 的独立 bounded recovery。
3. `ANTIGRAVITY_HOOK_DEPLOYMENT`：Global Hook 与 workspace-local Hook 的最终产品部署形式。

三项均不改变本 Contract 的 Completion Authority、状态映射或 bounded continuation 约束，也不阻塞本 Work Item 的设计审查。
