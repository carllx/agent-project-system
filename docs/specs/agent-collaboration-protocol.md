# Agent Collaboration Protocol Candidate v0.1

## Authority and scope

本 Spec 是 Agent Collaboration Framework 的通用 Review Protocol 权威。它定义 Execution Agent、Browser Lead 与用户之间的 Review 触发、最小消息 Contract、决策语义和完成权限；不定义 Transport、IDE、Hook、MCP、Plugin、持久化格式或具体运行模块。

`docs/specs/research-review-loop.md` 只定义 RR Lead 模块如何承载和映射本协议。Adapter 可以增加传输身份、封包或恢复字段，但不得改变本协议的 Review 与权限语义。

Protocol v0.1 的目标循环是：

```text
EXECUTE
→ REVIEW
→ REVISE
→ REVIEW
→ APPROVE
```

在用户授权的 Goal、Scope 和 Work Order 内，Execution Agent 默认自主执行。没有明确 Review Trigger 时，不为普通实现选择机械请求 Intermediate Review。

## Roles and authority

- **Execution Agent:** 执行授权工作、收集证据、报告不确定性，并可声明 `CLAIM_READY_FOR_REVIEW`。它不是 Completion Authority，禁止 `SELF_APPROVE_COMPLETION`。
- **Browser Lead:** 对 Review Request 做独立技术审查。在用户授权和既定 Acceptance Criteria 内拥有技术完成审查权；只有它对 Final Review 返回 `APPROVE`，Work Item 才允许完成。
- **User:** 保留 Goal、重大 Scope、成本、账号与权限、隐私、重大风险、产品方向和重大降级的最终决定权。Browser Lead 不是 User Authority。

Browser Lead 不得静默扩大 Goal、Scope 或 Acceptance Criteria。`USER_DECISION_REQUIRED` 必须映射为 `ESCALATE_TO_USER`。真正需要改变用户已批准 Scope 的 `SCOPE_CHANGE` 同样必须映射为 `ESCALATE_TO_USER`，Browser Lead 不得自行 `APPROVE`；仍在已授权 Scope 内的变化不得分类为 `SCOPE_CHANGE`。

## Review kinds and triggers

### Intermediate Review

Intermediate Review 用于执行中出现会实质影响既定计划、边界或验收的事件。v0.1 采用以下触发器：

- `PLAN_INVALIDATED`: 当前计划已无法合理满足 Goal 或 Acceptance Criteria，不是普通实现微调；仍可能存在授权范围内的新路径。
- `BLOCKER`: 当前授权范围内没有合理推进路径，不是首次命令失败或首次测试失败。
- `SCOPE_CHANGE`: 继续满足目标需要改变用户已批准 Scope；仍在已授权 Scope 内的变化不属于此 Trigger。
- `CRITICAL_VALIDATION_FAILURE`: 关键 Acceptance Evidence 失败并影响完成判断，不是普通首次失败或可直接修复的常规失败。
- `USER_DECISION_REQUIRED`: 问题落入用户保留权力边界，Execution Agent 必须停止自动执行。

`ARCHITECTURE_DECISION` 不作为 v0.1 的独立机械触发器。授权边界内的普通技术选择由 Execution Agent 自主完成；只有当架构问题同时构成上述触发器之一时才请求 Review。

### Final Review

Final Review 的唯一 v0.1 触发器是：

- `READY_FOR_COMPLETION`: Execution Agent 认为既定 Acceptance Criteria 已有充分证据，准备请求完成审查。

Execution Agent 此时只能把 `CLAIMED_STATUS` 设为 `CLAIM_READY_FOR_REVIEW`，Work Item 仍保持未完成。缺少相应 Final `APPROVE` 时，任何完成声明都无效。

## Review Request Contract

Review Request 是独立审查所需的最小事实快照，不是完整聊天记录。所有字段必填；没有内容的集合使用明确的 `NONE` 或空集合，不得省略。

```text
PROTOCOL_VERSION: ACF-0.1
WORK_ITEM_ID
REVIEW_REQUEST_ID
REVIEW_KIND: INTERMEDIATE / FINAL
REVIEW_TRIGGER
GOAL
ACCEPTANCE_CRITERIA
CURRENT_TASK
CHANGES
EVIDENCE
EXECUTION_ASSESSMENT:
  CLAIMED_STATUS: IN_PROGRESS / CLAIM_READY_FOR_REVIEW
  KNOWN_RISKS
  UNVERIFIED
  OPEN_QUESTIONS
  PROPOSED_NEXT_ACTION
```

Contract 规则：

- `REVIEW_REQUEST_ID` 在 Work Item 内唯一，使 Decision 能绑定具体请求而不依赖 Transport 顺序。
- `REVIEW_KIND=FINAL` 必须使用 `REVIEW_TRIGGER=READY_FOR_COMPLETION` 和 `CLAIMED_STATUS=CLAIM_READY_FOR_REVIEW`。
- `EVIDENCE` 只包含支持或反驳验收判断所需的可复查证据及其来源；不得用总结替代缺失证据。
- `UNVERIFIED` 必须显式列出。未知事实不得被推断为已通过。
- `PROPOSED_NEXT_ACTION` 是 Execution Agent 的建议，不约束 Browser Lead，也不授予新权限。

### Non-normative review artifact access note

Review Request 的既有 `EVIDENCE` 可以携带一个可选的 Review Artifact locator。此说明是 non-normative access guidance，不增加 ACF-0.1 的必填字段或 GitHub-specific schema；它只帮助 Browser Lead 取得被审查的真实产物，不改变 Review Decision、Completion Authority 或 Transport 语义。

当项目使用 Git 且 Browser Lead 可访问对应 GitHub 仓库时，优先提供已 push 的独立 Review Branch 与不可变 Commit SHA，避免在聊天中人工复制大量代码或 Diff。最小 locator 可以包含：

```text
REPOSITORY
REVIEW_BRANCH
COMMIT_SHA
BASELINE_SHA: optional
```

`COMMIT_SHA` 可作为本次 reviewed artifact identity，并是未来实现 stale approval enforcement 的候选输入；v0.1 不因此增加 hash、签名或 GitHub-specific Protocol 字段。GitHub 不是 Completion Authority、ACF Protocol 或实时 Transport，Branch/Commit 可访问也不等于 Review 已通过。没有 GitHub、Browser 无访问权或项目不使用 Git 时，继续使用 Evidence Packet 或 Manual Relay；不得为了使用该路径强制项目公开、上传或采用 Git。

## Review Decision Contract

Browser Lead 必须针对一个具体 Review Request 返回：

```text
PROTOCOL_VERSION: ACF-0.1
WORK_ITEM_ID
IN_REPLY_TO_REVIEW_REQUEST_ID
REVIEW_KIND: INTERMEDIATE / FINAL
REVIEW_DECISION: APPROVE / REVISE / ESCALATE_TO_USER
ACCEPTANCE_STATUS:
  - CRITERION
    STATUS: MET / NOT_MET / UNVERIFIED
    EVIDENCE
FINDINGS
REQUIRED_ACTIONS
DEBT
USER_DECISION_REQUIRED
```

Contract 规则：

- Review Decision 只有在 `PROTOCOL_VERSION`、`WORK_ITEM_ID`、`IN_REPLY_TO_REVIEW_REQUEST_ID` 和 `REVIEW_KIND` 同时与当前 Pending Request 精确匹配时才具有状态迁移权。旧回复、错 Work Item、错 Request ID、错 Review Kind 或错 Protocol Version 均为 `NON_AUTHORITATIVE`：不得改变 Execution State，当前 Review 保持 Pending；v0.1 不为这些情况增加更细错误枚举。
- `PASS_WITH_DEBT` 不是独立 Decision。非阻塞事项写入 `DEBT`，因此允许 `APPROVE + DEBT`。
- `DEBT` 不得隐藏未满足的 Acceptance Criterion，也不得静默增加新的完成条件。
- `ACCEPTANCE_STATUS` 必须覆盖每个 agreed Acceptance Criterion，且每项只能是 `MET`、`NOT_MET` 或 `UNVERIFIED`。Intermediate Review 可以包含 `NOT_MET` 或 `UNVERIFIED`。
- Final `APPROVE` 只允许在全部 agreed Acceptance Criteria 均为 `MET`、没有阻塞性 Finding、且不需要用户决定时返回。
- `REVISE` 必须给出非空 `REQUIRED_ACTIONS`；`ESCALATE_TO_USER` 必须明确 `USER_DECISION_REQUIRED`。
- 当 `REVIEW_TRIGGER` 为 `USER_DECISION_REQUIRED` 或 `SCOPE_CHANGE` 时，唯一允许的权威 Decision 是 `ESCALATE_TO_USER`。

## Decision behavior

### APPROVE

- `REVIEW_KIND=INTERMEDIATE`: Execution Agent 可以在现有用户授权范围内继续；该 Decision 不批准 Work Item 完成。
- `REVIEW_KIND=FINAL`: Work Item 才允许从 Review Pending 进入 Completed。`DEBT` 可记录后续非阻塞工作，但不能掩盖未满足验收。

### REVISE

- Work Item 保持未完成。
- Intermediate Review 被 `REVISE` 时，Execution Agent 必须在授权范围内执行 `REQUIRED_ACTIONS`、更新证据，并使用新的 `REVIEW_REQUEST_ID` 再次提交 Intermediate Review，进入 `INTERMEDIATE_REVIEW_PENDING`。
- Final Review 被 `REVISE` 时，Execution Agent 必须在授权范围内执行 `REQUIRED_ACTIONS`、更新证据，并使用新的 `REVIEW_REQUEST_ID` 再次提交 Final Review，进入 `FINAL_REVIEW_PENDING`。
- 重新提交的 Review 必须保持原 `REVIEW_KIND`。
- Execution Agent 不得跳过再次 Review，也不得因本地修复完成而结束 Work Item。

### ESCALATE_TO_USER

- 自动执行停止，Work Item 进入 Waiting for User。
- Browser Lead 说明需要用户决定的事项及影响，但不得代替用户选择。
- `WAITING_FOR_USER` 只有在获得当前 Work Item 的明确用户决定后才能恢复。该决定必须来自用户本人，Browser Lead 与 Execution Agent 均不得伪造。
- 收到用户决定后，Execution Agent 更新必要的 Goal、Scope 或 Constraints，再返回 Executing；不得从 Waiting for User 直接进入 Completed。
- 如果恢复执行后准备完成，仍必须使用新的 Final Review Request 重新进入 Final Review。

## State machine and completion invariant

```text
EXECUTING
  ├─ Intermediate Trigger → INTERMEDIATE_REVIEW_PENDING
  │    ├─ APPROVE → EXECUTING
  │    ├─ REVISE → REVISION_REQUIRED → EXECUTING → INTERMEDIATE_REVIEW_PENDING
  │    └─ ESCALATE_TO_USER → WAITING_FOR_USER
  └─ READY_FOR_COMPLETION → FINAL_REVIEW_PENDING
       ├─ APPROVE → COMPLETED
       ├─ REVISE → REVISION_REQUIRED → EXECUTING → FINAL_REVIEW_PENDING
       └─ ESCALATE_TO_USER → WAITING_FOR_USER
WAITING_FOR_USER
  └─ explicit decision from the User → UPDATE_GOAL_SCOPE_CONSTRAINTS → EXECUTING
```

强制不变量：

```text
COMPLETED
⇒ latest authoritative Review Decision is FINAL + APPROVE
⇒ every agreed Acceptance Criterion is MET
⇒ no unresolved User Decision exists
⇒ the approved Final Review Request still represents the current reviewed work state
```

Execution Agent 的 `CLAIM_READY_FOR_REVIEW` 只是状态声明，不满足上述不变量，也不能单独触发 Completed。

Final `APPROVE` 只授权完成其 `IN_REPLY_TO_REVIEW_REQUEST_ID` 所对应 Final Review Request 中被审查的工作状态。Final Review Request 发出后，如果 Execution Agent 对 Goal、Acceptance Criteria、实现结果、Changes 或 Evidence 作出足以影响审查结论的实质性修改，原 Final `APPROVE` 自动失效；必须用新的 `REVIEW_REQUEST_ID` 提交新的 Final Review Request，旧 `APPROVE` 不得用于进入 Completed。v0.1 只定义此语义，不引入 commit hash、snapshot hash、数据库 revision、签名或其他实现机制。

## Adapter mapping note

- OpenCLI 或其他 Transport 只能负责传递、身份绑定、重试与恢复，不属于本协议 schema。
- Antigravity 只是 Mapping Target。未来可把 `READY_FOR_COMPLETION` 映射为 Antigravity Stop Hook gate candidate，并在未获 Final `APPROVE` 时考虑 `decision=continue`；v0.1 不实现 Hook，也不把 Antigravity 字段写入通用 Contract。
- RR Lead 模块现有的 Packet、Envelope 和运行状态属于 RR-specific Adapter。其迁移到本 Candidate 的实现与兼容策略由后续 Work Item 决定。

## Falsifiable Lab handoff

第一条候选 Hypothesis：

> 给定一个 Acceptance Criterion 缺少证据的固定 Work Item，采用 Protocol v0.1 的 Execution Agent 会提交 Final `CLAIM_READY_FOR_REVIEW` 而不完成任务；Browser Lead 会返回 `REVISE` 和可执行的 `REQUIRED_ACTIONS`。补齐证据并再次 Final Review 后，只有匹配且仍代表当前被审查工作状态的 `APPROVE` 才允许进入 Completed。

该 Hypothesis 的失败条件至少包括：Final Approval 前出现完成状态、缺证据时返回 Final `APPROVE`、`REVISE` 没有 Required Actions、修订后未再次 Review、User Authority 问题未返回 `ESCALATE_TO_USER`，或 Final `APPROVE` 后发生影响被审查工作状态的实质性修改却仍使用旧 `APPROVE` 进入 Completed。Lab 设计与执行不属于本 Work Item。

## Open questions deferred from v0.1

- 通用协议是否需要独立的 Blocked/Unsafe 终止 Decision，先由真实实验观察，v0.1 不预置第四种 Decision。
- Review Request/Decision 的具体序列化格式与签名机制由 Adapter 实验决定。
- 多 Browser Lead、并行 Review、Quorum 与超时策略不进入 v0.1。
