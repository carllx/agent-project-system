# ADR 0004: Antigravity Completion-Gate Adapter

- **Status:** Proposed
- **Date:** 2026-08-09

## Context

ACF-0.1 已规定 Execution Agent 不是 Completion Authority，只有仍代表当前被审查工作状态的权威 Final `APPROVE` 才允许 Work Item 完成。Antigravity 2.6.0 Lab evidence 又证明 Global Stop Hook 能观察 Stop lifecycle，并通过 `decision=continue` 在同一 Conversation 中恢复 execution；系统实验也证明 `REVISION_REQUIRED` 下可 bounded continue，使 Agent 继续 Browser `REQUIRED_ACTIONS`。

但是 execution 自然停止与 Work Item 完成不是同一事件。若采用“没有 Final APPROVE 就永远 continue”，`FINAL_REVIEW_PENDING` 和 `WAITING_FOR_USER` 会形成无限唤醒；若任何 Stop 都直接放行并被解释为完成，则 Execution Agent 可以绕过 Browser Completion Authority。

## Decision

ACF Completion Authority 与 execution termination 解耦。正式产品采用 Antigravity Completion-Gate Adapter，把经 Orchestration 验证的 ACF Workflow State 映射到 Stop lifecycle：

- `EXECUTING`：存在可执行的当前必要动作且预算可用时 `CONTINUE_BOUNDED`；否则允许 Stop 但不完成 Work Item。
- `REVISION_REQUIRED`：Browser `REQUIRED_ACTIONS` 未完成且预算可用时 `CONTINUE_BOUNDED`；不可执行或预算耗尽时 `BLOCK_AND_ESCALATE`。
- `INTERMEDIATE_REVIEW_PENDING`、`FINAL_REVIEW_PENDING`、`WAITING_FOR_USER`：`ALLOW_STOP`，Work Item 保持未完成。
- `COMPLETED`：只有 ACF-0.1 的权威 Final Approval、Acceptance、User Authority 和 stale-approval 不变量全部验证后才能成立，随后 `ALLOW_STOP`。
- 未知、矛盾或不可验证状态：`BLOCK_AND_ESCALATE`，不得进入 `COMPLETED`。

Hook 本身不决定完成，只读取 ACF 状态并执行 Adapter Decision。bounded continuation 按当前必要动作设置有限预算，不能因自然 Stop 或 Hook 重启自动重置；耗尽后停止自动唤醒并转为 Blocker/Review。具体 Contract 由 `docs/specs/antigravity-completion-gate-adapter.md` 定义。

Transport 不属于 Completion Gate。OpenCLI `DELIVERY_UNKNOWN / BLOCKED` 作为独立问题处理，不得改变 Review authority 或阻塞 Adapter Productization。

## Alternatives considered

### 没有 Final APPROVE 就永远 continue

拒绝。它混淆 Work Item completion 与 execution liveness，使合法的 Browser/User 等待状态无限循环，也无法在动作不可执行时安全停止。

### Stop Hook 直接判断任务是否完成

拒绝。Hook 缺少独立 Review authority，不能替代 Browser Lead、补齐 Acceptance Evidence 或代替用户决定。

### 等 Transport 完成后再产品化 Completion Gate

拒绝。Transport 只承载消息，Completion Gate 只执行已存在的权威状态；两者可独立验证和演进。

## Evidence provenance and limits

- Bundle experiment label `ACF-AG-HOOK-GLOBAL-ANCHORED-005`；本机 observed evidence directory `ACF-AG-HOOK-GLOBAL-ANCHORED-V260-005`，Antigravity 2.6.0，路径 `E:\PROJECTS\rr-lead-skill-lab\experiments\ACF-AG-HOOK-GLOBAL-ANCHORED-V260-005\`：证明 Stop Hook 输入观察与同 Conversation 自动恢复可行。
- `ACF-AG-COMPLETION-GATE-SYSTEM-001`，产品基线 `af5d84afe314efaf9ee7bd2ad6080a032026a00d`，路径 `E:\PROJECTS\rr-lead-skill-lab\experiments\ACF-AG-COMPLETION-GATE-SYSTEM-001\`：证明 `REVISION_REQUIRED` 下 bounded continuation 可使 Agent 恢复执行 Required Actions。

Lab 是 Evidence Source，不是 Product implementation。当前证据不证明真实 DeepSeek premature-stop occurrence 的恢复、workspace-local Hook 的最终部署形式或 stale approval enforcement。

## Consequences

- ACF-0.1 保持 IDE/Transport 中立；Antigravity runtime 字段只存在于 Adapter Contract。
- execution 可以在 Review Pending 或 Waiting for User 时安全停止，而 Work Item 不会被误记为完成。
- 必须持久化最小 continuation state 和可审计决策证据；无限 continue 被正式禁止。
- 后续实现必须分别验证第三方模型 premature stop、Transport recovery 与 Hook deployment，但这些不阻塞本设计的产品化审查。
