# Diagnostic Batch Execution Packet

PACKET_TYPE: DIAGNOSTIC_BATCH_PACKET

PACKET_STATE: READY_NOT_STARTED

WORK_ITEM_ID: REAL-AGENT-REVIEW-LOOP-MVP-001

BATCH_ID: REAL-AGENT-REVIEW-LOOP-MVP-001-DIAG-BATCH-001

REQUIRED_PRODUCT_HEAD: 5bfa74e8c81f6679d397af375592512a8b614990

PRODUCT_ROOT: E:\PROJECTS\agent-project-system

LAB_ROOT: E:\PROJECTS\rr-lead-skill-lab

EVIDENCE_MATRIX_SCHEMA: docs/references/real-agent-review-loop-mvp-001-diagnostic-evidence-matrix.schema.json

EVIDENCE_MATRIX_CANONICAL_PATH: E:\PROJECTS\rr-lead-skill-lab\experiments\REAL-AGENT-REVIEW-LOOP-MVP-001-DIAG-BATCH-001\evidence-matrix.json

EVIDENCE_MATRIX_HUMAN_VIEW_PATH: E:\PROJECTS\rr-lead-skill-lab\experiments\REAL-AGENT-REVIEW-LOOP-MVP-001-DIAG-BATCH-001\evidence-matrix.md

## Bootstrap and authority

This Packet is the only active execution contract. A fresh Experiment Coordinator starts from `E:\PROJECTS\agent-project-system\AGENTS.md`, follows `docs/current.md` to the stable pointer, then executes only this Packet. Historical conversations, old Agent memory, and global workspace searches are not instruction sources.

Before any experiment action:

1. Confirm `WORK_ITEM_ID`, `BATCH_ID`, active pointer, Packet SHA-256, and `PACKET_STATE=READY_NOT_STARTED` all match.
2. Confirm Product branch is `work/real-agent-review-loop-mvp-001`, local Product HEAD equals its remote tracking ref, `REQUIRED_PRODUCT_HEAD` is an ancestor of that HEAD, and Product tracked files are unchanged.
3. Confirm Product authority is `PRODUCT_ROOT` and diagnostic mutation is limited to `LAB_ROOT`.
4. Create a new Batch-specific Lab directory only at the declared Evidence Matrix parent path. Never reuse Attempt 1 through 4 runtime roots, Message IDs, receipts, Transport state, or Conversations.
5. Validate the canonical Evidence Matrix against `EVIDENCE_MATRIX_SCHEMA` before each Batch round closes.

Any mismatch stops before a runtime Probe with `ACTIVE_EXECUTION_PACKET_INVALID`.

## Attempt 4 input fact

```text
ATTEMPT_ID: ATTEMPT-4
ATTEMPT_RESULT: CLEAN_FAIL
PROTOCOL_VIOLATION: NO
ROUND_1_WRITE_COUNT: 1
RESEND_PERFORMED: NO
FINAL_TRANSPORT_CLASSIFICATION: DELIVERY_UNKNOWN
PRIMARY_OBSERVED_BLOCKER: OpenCLI send returned non-success after /new preparation, and exact Delivery Conversation identity could not be established.
ROOT_CAUSE: UNRESOLVED
```

`DELIVERY_UNKNOWN` is not `FAILED`. No candidate mechanism below is a root cause until the Batch Evidence discriminates it.

## Objective

Explain why Product/OpenCLI send returned non-success after `/new` preparation and why exact Delivery Conversation identity could not be established. Optimize for information gain: distinguish competing hypotheses, shrink the UNKNOWN, identify the actual blocker, and only then decide whether Product code needs a separate change.

Getting the full Real Agent Loop to pass is not this Batch's primary objective.

## Initial competing hypotheses

- `H1`: Message injection did not succeed.
- `H2`: Message injection succeeded, but the send/click action did not succeed.
- `H3`: The message was sent, but OpenCLI lifecycle returned non-success before Delivery identity capture.
- `H4`: Browser window, tab, or session state did not match OpenCLI assumptions.
- `H5`: A Conversation was created or navigation occurred, but URL or Conversation identity discovery failed.
- `H6`: Send completed, but status/detail/read timing or lifecycle prevented Transport from proving Delivery.
- `H7`: The OpenCLI `/new → send → identity capture` state machine has an undiscovered boundary condition.
- `H8`: Another mechanism explains the observation; counter-hypotheses remain allowed.

The Coordinator may add or eliminate hypotheses only from recorded Evidence and may never exceed `MAX_HYPOTHESES`.

## Batch budget

```text
MAX_HYPOTHESES: 10
MAX_RUNTIME_PROBES: 3
MAX_BROWSER_WRITES: 2
MAX_SHARED_RUNTIME_WRITES: 4
MAX_SUBAGENTS: 5
MAX_BATCH_ROUNDS: 3
MAX_WALLCLOCK_MINUTES: 60
MAX_SEND_ATTEMPTS_PER_MESSAGE: 1
```

Every action counts from Batch start. Browser writes and shared-runtime mutations are hard ceilings, not targets. No unused budget may be transferred to another category or used to enlarge Product retry, recovery, detail, navigation, or command budgets.

## Work organization

The Coordinator may run bounded cognitive or read-only work in parallel:

- Product and frozen Transport source audit.
- Attempt 4 raw Evidence audit.
- OpenCLI command and lifecycle analysis.
- Browser window, tab, and session-state analysis.
- counter-hypothesis and adversarial review.
- minimum discriminating Probe design.

Shared-runtime Probes remain serial. A Probe that shares any Browser Conversation, window/tab, write receipt, Transport state, runtime root, Hook, workspace mutable state, or Evidence path may not overlap another Probe. Parallel Probes are allowed only when runtime root, message identity, Conversation/session resource, and Evidence path are all physically independent and attribution remains isolated.

Hard invariant:

```text
Sub-Agent autonomy
< Coordinator Batch Contract
< Browser Lead hard boundaries
```

## Coordinator authority

The Coordinator may propose hypotheses, select the next Probe, start read-only Sub-Agents, compare Evidence, eliminate hypotheses, and choose a next experiment within the fixed Contract.

The Coordinator must not modify Product source, frozen Transport, Loop Driver, guards, Completion Gate, receipts, or canonical Transport state; delete receipts; enlarge retry/time/recovery budgets; change Batch budget, forbidden actions, Evidence requirements, or stop conditions; run Attempt 5; or activate another Product Work Item.

If the next necessary action is a Product change, record the discriminating Evidence and stop with:

```text
STOP_BATCH_FOR_PRODUCT_CHANGE
```

The Runtime Experiment Agent must never repair Product and continue experimenting in the same Batch.

## Probe selection gate

Each runtime Probe must be the smallest action that distinguishes at least two still-plausible hypotheses. Before execution, record its question, expected discriminating outcomes, preconditions, control variables, resource isolation, exact authorized commands, Browser-write count, shared-mutation count, and stop conditions in the canonical Evidence Matrix.

Do not execute a Probe when source, existing Evidence, or a read-only audit already answers the question. Do not manufacture timeouts, navigation failures, or Browser state. Do not perform unplanned hello/test writes, same-ID resend, broad history scans, unrelated Conversation reads, arbitrary sleeps, unbounded polling, or ad hoc Product debugging.

## Evidence Matrix

The JSON at `EVIDENCE_MATRIX_CANONICAL_PATH` is the machine-readable runtime SSOT. It must validate against `EVIDENCE_MATRIX_SCHEMA`. The Markdown at `EVIDENCE_MATRIX_HUMAN_VIEW_PATH` is a generated or manually rendered view of the same JSON and may not add facts absent from JSON.

For every hypothesis and experiment record the schema-required identity, question, preconditions, control variables, procedure, raw Evidence paths, `PASS / FAIL / INCONCLUSIVE / BLOCKED` result, meaning, alternative explanations, confidence, contamination status, and next-best experiment. Raw Evidence remains in the Batch-specific Lab directory; do not copy unrelated Browser content or credentials.

The Batch final synthesis must explicitly state:

```text
WHAT_WAS_UNKNOWN_BEFORE
WHAT_IS_NOW_PROVEN
WHAT_IS_DISPROVEN
WHAT_REMAINS_INCONCLUSIVE
NEW_PROBLEMS_DISCOVERED
BEST_CURRENT_ROOT_CAUSE
ROOT_CAUSE_CONFIDENCE
PRODUCT_CHANGE_REQUIRED: YES / NO / INCONCLUSIVE
NEXT_HIGHEST_VALUE_ACTION
```

`BEST_CURRENT_ROOT_CAUSE` must remain `UNRESOLVED` unless attribution is supported by recorded Evidence. Confidence never upgrades Evidence strength.

## Mandatory stop conditions

Stop the Batch immediately and preserve current Evidence when:

- a hard budget is exhausted;
- Evidence attribution is ambiguous or shared environment contamination is detected;
- the next unknown requires changing this Contract, Product architecture, user permissions, or safety boundary;
- the next Probe could destroy or overwrite valid Evidence;
- a Product change is required;
- same-Message-ID resend or an unplanned Browser write would be required;
- a Probe violates its declared isolation or preconditions;
- Browser delivery becomes `DELIVERY_UNKNOWN` and no already-authorized read-only classification remains;
- a user-reserved decision is required.

Do not turn a stopped Batch into open-ended development. Return the Evidence Matrix, derived view, exact budget consumption, protocol violations, contamination status, and next highest-value action to the Project Agent and Browser Lead.

## Final output

Return:

```text
BATCH_ID
BATCH_RESULT: PASS / FAIL / INCONCLUSIVE / BLOCKED
BUDGET_USED
HYPOTHESES_RETAINED
HYPOTHESES_DISPROVEN
EXPERIMENT_RESULTS
WHAT_WAS_UNKNOWN_BEFORE
WHAT_IS_NOW_PROVEN
WHAT_IS_DISPROVEN
WHAT_REMAINS_INCONCLUSIVE
NEW_PROBLEMS_DISCOVERED
BEST_CURRENT_ROOT_CAUSE
ROOT_CAUSE_CONFIDENCE
PRODUCT_CHANGE_REQUIRED
NEXT_HIGHEST_VALUE_ACTION
EVIDENCE_MATRIX_CANONICAL_PATH
EVIDENCE_MATRIX_HUMAN_VIEW_PATH
CONTAMINATION_STATUS
PROTOCOL_VIOLATIONS
PRODUCT_REPOSITORY_STATUS
```

Do not declare `REAL-AGENT-REVIEW-LOOP-MVP-001` completed. Browser Lead and the Project Agent retain their existing authority boundaries.
