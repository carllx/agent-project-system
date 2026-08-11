# Antigravity Execution Packet: Attempt 4

PACKET_TYPE: ANTIGRAVITY_EXECUTION_PACKET

PACKET_STATE: READY_NOT_STARTED

PROTOCOL_VERSION: ACF-0.1

WORK_ITEM_ID: REAL-AGENT-REVIEW-LOOP-MVP-001

ATTEMPT_ID: ATTEMPT-4

REQUIRED_PRODUCT_HEAD: 17b74168f506a6c6ac5e12a69fe16bb79d2d46f1

REPOSITORY: E:\PROJECTS\agent-project-system

BRANCH: work/real-agent-review-loop-mvp-001

RUNTIME_ROOT: C:\Users\carll\AppData\Local\Temp\agent-project-system\REAL-AGENT-REVIEW-LOOP-MVP-001\attempt-4

## Goal

让真实 Antigravity Execution Agent 与独立 Browser GPT Supervisor 完成一次 `Execute → Review → Revise → Review → Approve` 协作循环，并且只有匹配的 Final Browser `APPROVE` 才能完成 Work Item。

The bounded runtime trace is:

```text
Execute
→ Final Review R1
→ authoritative REVISE
→ apply REQUIRED_ACTIONS
→ Final Review R2 with a new Request ID
→ authoritative APPROVE
→ Completion Gate permits COMPLETED
```

The execution task is to create immutable, repository-external Completion-Gate observation evidence. The Browser decision must be real; it must never be simulated locally.

## Acceptance Criteria

1. `AC1`: 一个真实小任务由 Antigravity Execution Agent 在明确 Goal、Scope 与 Acceptance Criteria 下执行，不以模拟结果替代。
2. `AC2`: Execution Agent 生成最小 ACF-0.1 Review Request 与可复查 Evidence，并通过冻结的 Product Transport 绑定到唯一 Browser Conversation。
3. `AC3`: Browser Lead 返回与 Protocol、Work Item、Request ID 和 Review Kind 匹配的 `REVISE`，且含可执行 `REQUIRED_ACTIONS`。
4. `AC4`: Browser Decision 被可靠带回 IDE execution state；Execution Agent 不自行批准，按 Required Actions 修订并使用新 Request ID 重新提交同类 Review。
5. `AC5`: Browser Lead 对修订后的 Final Request 返回权威 `APPROVE`，全部 agreed Acceptance Criteria 为 `MET`，无 unresolved User Decision。
6. `AC6`: Completion Gate 只在该匹配且未 stale 的 Final `APPROVE` 后允许 Work Item 完成；execution termination 不等于 Completion Authority。
7. `AC7`: 两轮传输保持 identity、same-Message-ID no-resend 和 `DELIVERY_UNKNOWN != FAILED`；Transport 若未暴露直接 blocker则不修改。
8. `AC8`: 真实 Loop Evidence、状态迁移、测试/检查与 Git artifact 可由 Browser Lead 独立复查，文档无重复 SSOT。

## Start State

```text
WORK_ITEM_STATE: IN_PROGRESS
WORKFLOW_STATE: EXECUTING
REVIEW_REQUEST_ID: NONE
ATTEMPT_STATE: NOT_STARTED
ROUND_1_REQUEST_ID: REAL-AGENT-REVIEW-LOOP-MVP-001-E2E-A4-R1-FINAL
ROUND_2_REQUEST_ID: REAL-AGENT-REVIEW-LOOP-MVP-001-E2E-A4-R2-FINAL
```

Attempt 4 has not started. Previous invalid attempts are not completion Evidence and must not be recovered or reused.

## Preflight

Before creating any runtime artifact or invoking any Product command:

1. Read `AGENTS.md`, `README.md`, `docs/index.md`, `docs/current.md`, this Packet, `docs/specs/agent-collaboration-protocol.md`, `docs/specs/research-review-loop.md`, and `docs/specs/antigravity-completion-gate-adapter.md`.
2. Confirm the active Work Item is exactly `REAL-AGENT-REVIEW-LOOP-MVP-001` and its state is `IN_PROGRESS`.
3. Confirm the current branch is `work/real-agent-review-loop-mvp-001`.
4. Confirm `REQUIRED_PRODUCT_HEAD` is an ancestor of current HEAD, current HEAD equals `origin/work/real-agent-review-loop-mvp-001`, and the worktree is clean.
5. Confirm `RUNTIME_ROOT` does not exist. Do not delete, move, or overwrite an existing directory.
6. Normalize this Packet to UTF-8 with LF newlines, then confirm its SHA-256 equals `ACTIVE_PACKET_SHA256` in `docs/references/current-execution-packet.md`.

If any check fails, stop with `ACTIVE_EXECUTION_PACKET_INVALID` before Browser/OpenCLI write count becomes nonzero.

## Hard Boundaries

- Do not modify, stage, commit, or push any repository file.
- Do not modify Completion Gate, Review Loop, Stop Hook, Adapter, Skill, or frozen Transport.
- Do not read Antigravity brain logs, historical transcripts, or private conversation memory to recover instructions.
- Do not call `opencli` or the frozen Transport directly. Use only `scripts/acf_review_loop.py` Product commands specified below.
- Do not manually type or paste a Review Request into Browser.
- Do not delete, move, rename, or edit canonical Loop/Transport state or Browser message artifacts after creation.
- Do not pass budget override flags. Do not add polling, sleep, retry, or recovery beyond the Product command path.
- Each Review Request ID may cause at most one write. A non-success `send-review` result never authorizes resend.
- At most two Browser writes are authorized: one for Round 1 and one for Round 2 after an authoritative `REVISE`.
- `DELIVERY_UNKNOWN` is not `FAILED`; stop and report it without resending.
- Do not start the next Product Work Item or the Experiment Batch requirement.

## Allowed Actions

- Read repository authority files and source needed to execute these exact commands.
- Create immutable Attempt 4 artifacts only under `RUNTIME_ROOT`.
- Run the repository Product driver with default budgets.
- Run read-only Git checks and local SHA-256 calculation.
- Apply a Browser `REVISE` only through the Product state transition and only within the repository-external observation artifact scope.
- Report exact command results and artifact paths.

## Runtime Contract

Create `contract.json` under `RUNTIME_ROOT` with exactly this Work Item, Goal, and the eight Acceptance Criteria above. Use JSON objects of the form:

```json
{
  "WORK_ITEM_ID": "REAL-AGENT-REVIEW-LOOP-MVP-001",
  "GOAL": "让真实 Antigravity Execution Agent 与独立 Browser GPT Supervisor 完成一次 Execute → Review → Revise → Review → Approve 协作循环，并且只有匹配的 Final Browser APPROVE 才能完成 Work Item。",
  "ACCEPTANCE_CRITERIA": [
    {"CRITERION": "AC1", "DESCRIPTION": "一个真实小任务由 Antigravity Execution Agent 在明确 Goal、Scope 与 Acceptance Criteria 下执行，不以模拟结果替代。"},
    {"CRITERION": "AC2", "DESCRIPTION": "Execution Agent 生成最小 ACF-0.1 Review Request 与可复查 Evidence，并通过冻结的 Product Transport 绑定到唯一 Browser Conversation。"},
    {"CRITERION": "AC3", "DESCRIPTION": "Browser Lead 返回与 Protocol、Work Item、Request ID 和 Review Kind 匹配的 REVISE，且含可执行 REQUIRED_ACTIONS。"},
    {"CRITERION": "AC4", "DESCRIPTION": "Browser Decision 被可靠带回 IDE execution state；Execution Agent 不自行批准，按 Required Actions 修订并使用新 Request ID 重新提交同类 Review。"},
    {"CRITERION": "AC5", "DESCRIPTION": "Browser Lead 对修订后的 Final Request 返回权威 APPROVE，全部 agreed Acceptance Criteria 为 MET，无 unresolved User Decision。"},
    {"CRITERION": "AC6", "DESCRIPTION": "Completion Gate 只在该匹配且未 stale 的 Final APPROVE 后允许 Work Item 完成；execution termination 不等于 Completion Authority。"},
    {"CRITERION": "AC7", "DESCRIPTION": "两轮传输保持 identity、same-Message-ID no-resend 和 DELIVERY_UNKNOWN != FAILED；Transport 若未暴露直接 blocker则不修改。"},
    {"CRITERION": "AC8", "DESCRIPTION": "真实 Loop Evidence、状态迁移、测试/检查与 Git artifact 可由 Browser Lead 独立复查，文档无重复 SSOT。"}
  ]
}
```

Initialize exactly once:

```powershell
python scripts/acf_review_loop.py initialize --contract "$runtimeRoot\contract.json" --state "$runtimeRoot\loop-state.json"
```

Any nonzero Product command exit is a hard stop unless the command is the one authorized bounded `recover-review` described below.

## Real Task and Round 1 Artifact

Using repository source at the current checked-out HEAD, import `base_state` and `evaluate_completion_gate` from `runtime.completion_gate`. Create immutable `completion-gate-observation-r1.json` containing:

- Work Item and Attempt identity.
- exact current Git HEAD and required Product head.
- the complete input state for `UNRESOLVED_USER_DECISION=true`.
- the complete returned Completion-Gate decision.
- `UNVERIFIED_STRING_CASE: NOT_OBSERVED_IN_R1`.
- a truthful statement that no Browser decision has yet been received.

The observation must come from executing the actual Product Policy. Do not hand-author the expected output. Do not include credentials, Browser content, or private transcript content.

Compute the lowercase SHA-256 of the exact artifact bytes. That hash is `ROUND_1_ARTIFACT_ID`. Do not edit the artifact after hashing.

Create `request-r1.json` with:

```text
PROTOCOL_VERSION: ACF-0.1
WORK_ITEM_ID: REAL-AGENT-REVIEW-LOOP-MVP-001
REVIEW_REQUEST_ID: REAL-AGENT-REVIEW-LOOP-MVP-001-E2E-A4-R1-FINAL
REVIEW_KIND: FINAL
REVIEW_TRIGGER: READY_FOR_COMPLETION
GOAL: exact Runtime Contract Goal
ACCEPTANCE_CRITERIA: exact Runtime Contract criteria snapshot
CURRENT_TASK: Independently review Round 1 Completion-Gate observation and the real-loop evidence.
CHANGES: repository-external immutable Round 1 observation only
EVIDENCE: artifact path, SHA-256, exact Product head, relevant local check results
EXECUTION_ASSESSMENT.CLAIMED_STATUS: CLAIM_READY_FOR_REVIEW
EXECUTION_ASSESSMENT.KNOWN_RISKS: NONE
EXECUTION_ASSESSMENT.UNVERIFIED: UNVERIFIED string case is intentionally absent from Round 1 evidence
EXECUTION_ASSESSMENT.OPEN_QUESTIONS: Does the Browser require that missing observation before approval?
EXECUTION_ASSESSMENT.PROPOSED_NEXT_ACTION: Browser Final Review
```

Submit the request once:

```powershell
python scripts/acf_review_loop.py submit-review --state "$runtimeRoot\loop-state.json" --request "$runtimeRoot\request-r1.json" --artifact-id "<ROUND_1_ARTIFACT_ID>"
```

Send it once and only once:

```powershell
python scripts/acf_review_loop.py send-review --state "$runtimeRoot\loop-state.json" --runtime-dir "$runtimeRoot\review-runtime" --prepare-new
```

The canonical Round 1 artifacts are:

```text
review-runtime\REAL-AGENT-REVIEW-LOOP-MVP-001-E2E-A4-R1-FINAL.message.txt
review-runtime\REAL-AGENT-REVIEW-LOOP-MVP-001-E2E-A4-R1-FINAL.transport.json
```

Do not reconstruct, replace, move, or resend either artifact.

If the Transport state is `RESPONSE_PENDING` after one write, exactly one no-write continuation is allowed:

```powershell
python scripts/acf_review_loop.py recover-review --state "$runtimeRoot\loop-state.json" --transport-state "$runtimeRoot\review-runtime\REAL-AGENT-REVIEW-LOOP-MVP-001-E2E-A4-R1-FINAL.transport.json"
```

No other non-success state authorizes retry or resend. Stop and report exact evidence.

Before ingest, recompute the current artifact SHA-256. If it differs from `ROUND_1_ARTIFACT_ID`, run `mark-stale` and stop. Otherwise ingest exactly once:

```powershell
python scripts/acf_review_loop.py ingest-review --state "$runtimeRoot\loop-state.json" --transport-state "$runtimeRoot\review-runtime\REAL-AGENT-REVIEW-LOOP-MVP-001-E2E-A4-R1-FINAL.transport.json" --current-artifact-id "<ROUND_1_ARTIFACT_ID>"
```

## Required Round 1 Outcome

Continue only if Product state proves all of the following:

```text
AUTHORITATIVE: true
REVIEW_DECISION: REVISE
WORKFLOW_STATE: REVISION_REQUIRED
CURRENT_REQUIRED_ACTION: nonempty and within the allowed artifact scope
```

`APPROVE`, `ESCALATE_TO_USER`, `NON_AUTHORITATIVE`, a mismatched binding, or a Required Action outside this Packet is a hard stop. Do not invent a revision.

## Revision and Round 2

Apply only the authoritative `CURRENT_REQUIRED_ACTION`. The expected bounded revision is to create a new immutable `completion-gate-observation-r2.json` that retains the Round 1 observation and adds the actual Product Policy result for the string-valued `UNRESOLVED_USER_DECISION="UNVERIFIED"` case. Never edit the Round 1 artifact.

Record the applied revision with concrete artifact/hash evidence:

```powershell
python scripts/acf_review_loop.py revision-applied --state "$runtimeRoot\loop-state.json" --evidence "Created immutable Round 2 observation at <PATH> with SHA-256 <ROUND_2_ARTIFACT_ID> by applying the authoritative Required Action."
```

Create `request-r2.json` with the same exact Goal and Acceptance Criteria, a new Request ID, the new artifact/hash Evidence, and the same `FINAL` Review Kind:

```text
REVIEW_REQUEST_ID: REAL-AGENT-REVIEW-LOOP-MVP-001-E2E-A4-R2-FINAL
REVIEW_KIND: FINAL
REVIEW_TRIGGER: READY_FOR_COMPLETION
CLAIMED_STATUS: CLAIM_READY_FOR_REVIEW
PROPOSED_NEXT_ACTION: Browser Final Review
```

Submit and send exactly once, using the verified Round 1 Transport state as the continuation target:

```powershell
python scripts/acf_review_loop.py submit-review --state "$runtimeRoot\loop-state.json" --request "$runtimeRoot\request-r2.json" --artifact-id "<ROUND_2_ARTIFACT_ID>"
python scripts/acf_review_loop.py send-review --state "$runtimeRoot\loop-state.json" --runtime-dir "$runtimeRoot\review-runtime" --previous-transport-state "$runtimeRoot\review-runtime\REAL-AGENT-REVIEW-LOOP-MVP-001-E2E-A4-R1-FINAL.transport.json"
```

If and only if Round 2 is `RESPONSE_PENDING`, use the same single bounded `recover-review` rule with the Round 2 Transport state. Never resend.

Recompute the Round 2 artifact hash before ingest. A mismatch requires `mark-stale` and a hard stop. Otherwise ingest exactly once with the Round 2 artifact ID.

## Completion Authority

Attempt 4 succeeds only when the persisted Product state proves:

```text
ROUND_1: authoritative Final REVISE with executable REQUIRED_ACTIONS
ROUND_2: authoritative Final APPROVE bound to the new Request ID
ACCEPTANCE_STATUS: AC1 through AC8 each uniquely MET with nonempty Evidence
UNRESOLVED_USER_DECISION: false
REVIEWED_STATE_CURRENT: locally derived true
COMPLETION_GATE_DECISION: ALLOW_STOP
WORKFLOW_STATE: COMPLETED
```

An IDE permission approval, Browser navigation, Transport `work_item_state`, Agent self-report, natural stop, or old approval is never Completion Authority.

## Evidence Required

Return exact, non-secret evidence for:

- preflight branch, HEAD, remote equality, clean status, and required Product-head ancestry;
- Packet SHA-256 match;
- Round 1 and Round 2 artifact paths and SHA-256 values;
- each Review Request ID and reviewed artifact identity;
- each Product command exit code;
- each Transport `message_send_count` and verified delivery Conversation ID;
- authoritative Decision binding fields;
- Required Action and revision evidence;
- state transitions through `FINAL_REVIEW_PENDING`, `REVISION_REQUIRED`, `EXECUTING`, `FINAL_REVIEW_PENDING`, and `COMPLETED`;
- Completion Gate result and final Work Item state;
- repository worktree remaining clean and unchanged.

## When to Stop

Stop immediately without additional Browser/OpenCLI writes if:

- bootstrap preflight fails;
- any forbidden action would be required;
- a Product command fails outside the single permitted pending-response recovery;
- delivery is unknown, misrouted, conflicting, or marker verification fails;
- a Decision is non-authoritative, stale, mismatched, or not the required Round outcome;
- the Required Action changes Goal, Scope, Acceptance Criteria, Product source, Transport, or another canonical artifact;
- either Message ID has already been written once;
- an unresolved User Decision appears;
- evidence attribution becomes uncertain.

Report the exact stop reason and observed evidence. Do not repair the protocol by ad hoc commands.
