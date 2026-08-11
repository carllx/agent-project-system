# Real Agent Review Loop Acceptance Packet

PACKET_TYPE: REAL_AGENT_REVIEW_LOOP_ACCEPTANCE_PACKET

PACKET_STATE: READY_NOT_STARTED

WORK_ITEM_ID: REAL-AGENT-REVIEW-LOOP-MVP-001

ACCEPTANCE_RUN_ID: REAL-AGENT-REVIEW-LOOP-MVP-001-ACCEPTANCE-002

REQUIRED_PRODUCT_HEAD: 7eead49dec3421c1aa7f6fb21be90091454754e4

PRODUCT_ROOT: E:\PROJECTS\agent-project-system

RUNTIME_ROOT: C:\Users\carll\AppData\Local\Temp\agent-project-system\REAL-AGENT-REVIEW-LOOP-MVP-001\acceptance-002

ROUND_1_REQUEST_ID: REAL-AGENT-REVIEW-LOOP-MVP-001-acceptance-002-R1-FINAL

ROUND_2_REQUEST_ID: REAL-AGENT-REVIEW-LOOP-MVP-001-acceptance-002-R2-FINAL

## Authority and start gate

This Packet is prepared only. Do not start it merely because the Packet exists. A fresh Coordinator may start only after the user or designated project authority explicitly authorizes this Acceptance Run.

At start, read `AGENTS.md`, `README.md`, `docs/index.md`, `docs/current.md`, this Packet, `docs/specs/agent-collaboration-protocol.md`, `docs/specs/research-review-loop.md`, and `docs/specs/antigravity-completion-gate-adapter.md`. Do not recover instructions from historical transcripts, Agent memory, Browser history, or the completed Diagnostic Batch.

Before any runtime artifact or Browser write:

1. Confirm the active Work Item and Packet pointer match this Packet and `PACKET_STATE=READY_NOT_STARTED`.
2. Confirm branch `work/real-agent-review-loop-mvp-001`, clean tracked files, local HEAD equals its remote tracking ref, and `REQUIRED_PRODUCT_HEAD` is an ancestor of HEAD.
3. Confirm `RUNTIME_ROOT` does not exist. Do not reuse prior state, receipt, Message ID, Request ID, artifact, or Conversation.
4. Confirm repository source is the Product authority. Installed or Lab copies are not substitutes.
5. Stop as `ACTIVE_EXECUTION_PACKET_INVALID` on any mismatch.

## Objective and real task

Complete one real four-turn minimum loop:

```text
Turn 1: Execution Agent executes the real task and sends Final Review R1
Turn 2: Browser RR Lead returns authoritative REVISE
Turn 3: Execution Agent applies the required action and sends revised Final Review R2
Turn 4: Browser RR Lead returns authoritative APPROVE and Completion Gate reaches COMPLETED
```

The real task is to execute the actual Product Completion-Gate policy and create immutable repository-external observation evidence. Round 1 records the normal base-state result. The authoritative Round 1 Required Action must be applied within this evidence scope; the bounded expected revision is a new immutable Round 2 observation that retains Round 1 evidence and adds the actual Policy result for string-valued `UNRESOLVED_USER_DECISION="UNVERIFIED"`. Do not hand-author Policy results and do not edit Round 1 after hashing.

## Acceptance criteria

1. A real Antigravity Execution Agent performs the task under this Goal and scope; no local simulation substitutes for Browser decisions.
2. R1 is delivered once to one newly established Browser Conversation and ingested as identity-bound authoritative `REVISE` with nonempty in-scope `REQUIRED_ACTIONS`.
3. The required action is actually applied and recorded with immutable artifact/hash Evidence.
4. R2 uses a different Request ID and Message ID, the same `FINAL` Review Kind, and the exact same Browser Conversation through the verified continuation target.
5. R2 is delivered once and ingested as identity-bound authoritative `APPROVE`; all agreed criteria are `MET`, blockers and user decisions are `NONE`.
6. R1 and R2 each have write count `1`; neither Message ID is resent. A timeout, nonzero return, `DELIVERY_UNKNOWN`, mismatch, stale artifact, or ambiguous response never authorizes resend.
7. Both Browser decisions are ingested through `scripts/acf_review_loop.py`; Execution Agent never self-approves and Transport labels never become Completion Authority.
8. Completion Gate reaches `COMPLETED` only after the current, matching Final `APPROVE`; the real `Execute → Review → Revise → Review → Approve` loop is validated.

## Hard boundaries

- At most two Browser writes are authorized: one R1 write and one R2 write after authoritative R1 `REVISE`.
- Do not call OpenCLI or `opencli_transport.py` directly. Use only the Product driver `scripts/acf_review_loop.py` with default bounded budgets.
- Do not modify Transport, Review Loop, Completion Gate, Stop Hook, Adapter, Skill, Specs, Packet, pointer, or repository files during the run.
- Do not pass timeout/budget overrides, add sleeps or polling, delete receipts, manufacture a timeout, or use manual relay.
- `DELIVERY_UNKNOWN != FAILED`; preserve evidence and stop without resend.
- Do not merge, close the Work Item, start another Work Item, or claim completion without authoritative Final Browser `APPROVE`.
- Browser Transport Conversation and Antigravity Execution Conversation remain distinct resources.

## Runtime contract

Create `contract.json` in the new `RUNTIME_ROOT` with the exact Work Item, Goal, and the eight criteria above. Initialize the loop state only through the Product driver. Create Round 1 evidence by importing and executing `base_state` and `evaluate_completion_gate` from `runtime.completion_gate`; persist the exact input and returned result in immutable `completion-gate-observation-r1.json`, then compute its lowercase SHA-256.

Create `request-r1.json` with:

```text
PROTOCOL_VERSION: ACF-0.1
WORK_ITEM_ID: REAL-AGENT-REVIEW-LOOP-MVP-001
REVIEW_REQUEST_ID: REAL-AGENT-REVIEW-LOOP-MVP-001-acceptance-002-R1-FINAL
REVIEW_KIND: FINAL
REVIEW_TRIGGER: READY_FOR_COMPLETION
CURRENT_TASK: Independently review Round 1 Completion-Gate observation and real-loop evidence.
CHANGES: repository-external immutable Round 1 observation only
EVIDENCE: exact artifact path, SHA-256, Product head, and relevant local checks
EXECUTION_ASSESSMENT.CLAIMED_STATUS: CLAIM_READY_FOR_REVIEW
```

The Goal and Acceptance Criteria snapshot must exactly match `contract.json`. Submit R1, then execute one `send-review --prepare-new`. Its canonical generated Message ID must be unique to R1. If the bounded Product path reports response pending, only the driver-authorized no-write continuation may be used; no other retry or resend is allowed.

Before ingest, recompute the Round 1 artifact hash. Ingest exactly one matching Transport response. The only valid continuation outcome is:

```text
AUTHORITATIVE: true
REVIEW_DECISION: REVISE
WORKFLOW_STATE: REVISION_REQUIRED
CURRENT_REQUIRED_ACTION: nonempty and within the evidence-only scope
```

Any other R1 outcome is a hard stop.

Apply exactly the authoritative Required Action. Create immutable `completion-gate-observation-r2.json`, compute its SHA-256, and record the revision with `revision-applied` and concrete evidence. Never mutate the R1 artifact.

Create `request-r2.json` with the same Goal, criteria, `FINAL` Review Kind, and:

```text
REVIEW_REQUEST_ID: REAL-AGENT-REVIEW-LOOP-MVP-001-acceptance-002-R2-FINAL
CURRENT_TASK: Independently review the revised Completion-Gate observation and complete the real loop only if every criterion is met.
CHANGES: authoritative Round 1 Required Action applied in a new immutable Round 2 observation
EVIDENCE: R1 and R2 artifact paths and hashes, applied-action evidence, Product head, and exact R1 decision binding
```

Submit R2 and execute one `send-review` using the verified R1 Transport state as `--previous-transport-state`. Do not use `--prepare-new`; the derived target must equal the R1 Delivery Conversation. Before ingest, recompute the R2 hash. Ingest exactly one matching response.

## Required final gate

The run passes only when all fields below are proven from runtime state and immutable artifacts:

```text
LOGICAL_TURN_COUNT: AT_LEAST_4
ROUND_1_DECISION: REVISE
ROUND_1_AUTHORITATIVE: YES
ROUND_2_DECISION: APPROVE
ROUND_2_AUTHORITATIVE: YES
SAME_BROWSER_CONVERSATION: YES
DISTINCT_MESSAGE_IDS: YES
ROUND_1_WRITE_COUNT: 1
ROUND_2_WRITE_COUNT: 1
RESEND_PERFORMED: NO
ROUND_1_REQUIRED_ACTION_APPLIED: YES
BOTH_DECISIONS_INGESTED: YES
COMPLETION_GATE: COMPLETED
REAL_AGENT_REVIEW_LOOP_VALIDATED: YES
```

An `APPROVE` with missing/duplicate criteria, blockers, unresolved user decision, stale artifact, wrong identity, wrong Conversation, wrong Request ID, wrong Review Kind, or non-current state is non-authoritative and cannot complete the Work Item.

## Stop report

On any hard stop, report the exact phase, command exit, state path, Transport classification, Conversation identities, write counts, receipt state, Message IDs, whether a Browser response was ingested, and why continuation is forbidden. Preserve all valid evidence. Do not repair Product or start a replacement run inside this Packet.
