# Real Agent Review Loop Manual Relay Acceptance Contract

PACKET_TYPE: REAL_AGENT_REVIEW_LOOP_MANUAL_RELAY_PACKET

PACKET_STATE: READY_NOT_STARTED

MANUAL_RELAY_ACCEPTANCE_READY: YES

WORK_ITEM_ID: REAL-AGENT-REVIEW-LOOP-MVP-001

ACCEPTANCE_RUN_ID: REAL-AGENT-REVIEW-LOOP-MVP-001-ACCEPTANCE-MANUAL-003

TRANSPORT_MODE: MANUAL_RELAY

BROWSER_RESPONSE_PRESENTATION: COPY_SAFE_PLAIN_TEXT_BLOCK

REQUIRED_PRODUCT_HEAD: ed616125fc0e7ff35464dd4dbe1b67e1f5c3d921

PRODUCT_ROOT: E:\PROJECTS\agent-project-system

RUNTIME_ROOT: %TEMP%\agent-project-system\REAL-AGENT-REVIEW-LOOP-MVP-001\acceptance-manual-003

ROUND_1_REQUEST_ID: REAL-AGENT-REVIEW-LOOP-MVP-001-ACCEPTANCE-MANUAL-003-R1-FINAL

ROUND_2_REQUEST_ID: REAL-AGENT-REVIEW-LOOP-MVP-001-ACCEPTANCE-MANUAL-003-R2-FINAL

## Previous run closeout

The earlier Manual Relay Acceptance runs are closed and must never be resumed.

First run:

```text
RESULT: CLEAN_HARD_STOP
PHASE: R1_MANUAL_RESPONSE_INGEST
PRODUCT_PARSER_FAILURE: NO
BROWSER_DECISION_INGESTED: NO
CAUSE: MANUAL_RELAY_COPY_FORMAT_CORRUPTION
STRICT_RR_PARSER_BEHAVIOR: CORRECT
PARSER_RELAXATION_AUTHORIZED: NO
```

The copied response had later top-level fields indented as continuation content beneath the final Acceptance Status item. The strict parser correctly returned `RR response fields are incomplete`. Preserve that failed runtime as incident Evidence; do not reuse its state, raw response, Request IDs, or artifacts.

Second run:

```text
RUN_ID: REAL-AGENT-REVIEW-LOOP-MVP-001-ACCEPTANCE-MANUAL-002
RESULT: CLEAN_HARD_STOP
PHASE: R2_FINAL_BROWSER_REVIEW
FAILURE_CLASSIFICATION: FINAL_ACCEPTANCE_CRITERIA_CIRCULAR_DEPENDENCY
TRANSPORT_FAILURE: NO
MANUAL_INGEST_FAILURE: NO
PARSER_FAILURE: NO
BROWSER_DECISION_INGESTED: R1 YES; R2 AUTHORITATIVE REVISE
```

Manual-002 proved the real path through authoritative R1 `REVISE`, applied Required Action, R2 generation, same user-maintained Browser Conversation, and authoritative R2 `REVISE`. It stopped because its Browser criteria required the not-yet-produced Final approval, R2 ingest provenance, and Completion Gate result as preconditions for that same approval. Preserve its complete runtime as valid Evidence; never mutate or resume it.

## Authority and start gate

This Packet is prepared, not started. A fresh Execution Agent may begin only after the user or Browser Lead explicitly starts this Acceptance Run. Read `AGENTS.md`, `README.md`, `docs/index.md`, `docs/current.md`, the active pointer, this Packet, and the applicable ACF/RR Specs. Historical conversations and Agent memory are not execution authority.

Before creating runtime artifacts:

1. Confirm this is the active Packet and its state is `READY_NOT_STARTED`.
2. Confirm branch `work/real-agent-review-loop-mvp-001`, a clean worktree, local HEAD equal to the remote tracking ref, and `REQUIRED_PRODUCT_HEAD` an ancestor of HEAD.
3. Confirm `RUNTIME_ROOT` does not exist. Never reuse an earlier state, Request ID, response, or artifact.
4. Use repository source as Product authority.
5. Stop as `ACTIVE_EXECUTION_PACKET_INVALID` on any mismatch.

## Goal and two-gate acceptance model

Run one real four-turn minimum collaboration loop:

```text
Turn 1: Execution Agent executes the evidence task and submits Final R1
Turn 2: independent Browser Lead returns authoritative REVISE
Turn 3: Execution Agent applies REQUIRED_ACTIONS and submits Final R2
Turn 4: the same Browser Lead Conversation returns authoritative APPROVE
```

The real task is to execute the Product Completion-Gate policy and preserve immutable, repository-external observations. R1 records the base-state policy result. The Browser must identify a concrete evidence deficiency and return an executable in-scope revision. The expected bounded revision is a new immutable R2 observation that preserves R1 and adds the policy result for string-valued `UNRESOLVED_USER_DECISION="UNVERIFIED"`. Do not hand-author policy results.

The run has two separate gates. Gate A contains only facts already observable before the Browser produces its current Decision. Gate B runs only after the user returns the Browser's Final response. Never move a Gate B fact into Browser `ACCEPTANCE_STATUS`.

### GATE_A_BROWSER_FINAL_REVIEW

These are the eight agreed criteria stored in `contract.json` and reviewed in both rounds:

1. `AC1`: a real Antigravity Execution Agent performed this evidence task; no Browser Decision was simulated locally.
2. `AC2`: R1 returned through Manual Relay and Product strictly ingested it as authoritative `REVISE` with executable Required Actions.
3. `AC3`: the exact R1 Required Actions were actually applied and produced new immutable R2 Evidence.
4. `AC4`: R2 uses a different Request ID, preserves `FINAL` Review Kind, and the user continued in the same Browser Lead Conversation used for R1.
5. `AC5`: R2 Review Request provides concrete reviewable revision Evidence: R1 artifact path/hash, R1 Decision identity/provenance, exact Required Action, R2 artifact path/hash, actual typed R2 input, actual policy result, revision-applied Evidence, and Product head.
6. `AC6`: the R1 raw Browser response is preserved byte-for-byte with `MANUAL_RELAY` provenance, and the R1 reviewed artifact remains unchanged.
7. `AC7`: the Execution Agent has not self-approved; Browser Final Decision remains Completion Authority.
8. `AC8`: the current R2 reviewed artifact is current, has no unresolved blocker or User Decision Required, and contains enough existing Evidence for the Browser to judge whether the revision satisfies the Goal.

Gate A Final `APPROVE` requires all eight criteria `MET`, concrete Evidence for each, no blockers, no Required Actions, and no User Decision Required. In R1, criteria that depend on the not-yet-performed revision must remain `NOT_MET` or `UNVERIFIED`, so the expected independent Decision is `REVISE`.

### GATE_B_POST_INGEST_COMPLETION_VERIFICATION

Gate B is Product/runtime verification after the Final Browser response returns. These are not Browser Acceptance Status criteria:

```text
POST_INGEST_1: R2 raw Browser response is preserved byte-for-byte.
POST_INGEST_2: REVIEW_HISTORY contains R2 MANUAL_REVIEW_INGESTED provenance.
POST_INGEST_3: R2 is strictly ingested as authoritative APPROVE against the current artifact.
POST_INGEST_4: WORKFLOW_STATE and Completion Gate result are COMPLETED.
POST_INGEST_5: Execution Agent did not self-approve.
POST_INGEST_6: final report preserves the exact Manual/automated validation boundaries.
```

If any Gate B check fails, set `RUN_RESULT: POST_INGEST_COMPLETION_FAILURE`, preserve the Browser's historical Decision unchanged, and stop. Never fabricate Gate A `MET` values to satisfy Gate B.

## Runtime artifacts and Product commands

Create the new `RUNTIME_ROOT`. Its required artifacts are:

```text
contract.json
state.json
completion-gate-observation-r1.json
request-r1.json
r1-browser-relay-packet.txt
r1-browser-response.txt
completion-gate-observation-r2.json
request-r2.json
r2-browser-relay-packet.txt
r2-browser-response.txt
final-report.txt
```

Create `contract.json` with `PROTOCOL_VERSION=ACF-0.1`, this exact Work Item ID, the Goal above, and the eight exact criteria. Initialize once:

```powershell
python scripts/acf_review_loop.py initialize --contract "$env:TEMP\agent-project-system\REAL-AGENT-REVIEW-LOOP-MVP-001\acceptance-manual-003\contract.json" --state "$env:TEMP\agent-project-system\REAL-AGENT-REVIEW-LOOP-MVP-001\acceptance-manual-003\state.json"
```

Execute `runtime.completion_gate.base_state()` and `evaluate_completion_gate()` from repository source. Save the exact input and result as immutable R1 JSON and calculate its lowercase SHA-256. Create `request-r1.json` with the exact Goal/criteria snapshot and:

```text
PROTOCOL_VERSION: ACF-0.1
WORK_ITEM_ID: REAL-AGENT-REVIEW-LOOP-MVP-001
REVIEW_REQUEST_ID: REAL-AGENT-REVIEW-LOOP-MVP-001-ACCEPTANCE-MANUAL-003-R1-FINAL
REVIEW_KIND: FINAL
REVIEW_TRIGGER: READY_FOR_COMPLETION
CURRENT_TASK: Independently review the R1 Completion-Gate observation and Manual Relay loop evidence.
CHANGES: repository-external immutable R1 observation only
EVIDENCE: exact R1 path, SHA-256, Product head, and local checks
EXECUTION_ASSESSMENT.CLAIMED_STATUS: CLAIM_READY_FOR_REVIEW
```

Set `$r1Sha256` to the computed R1 artifact SHA-256. Submit and render R1:

```powershell
python scripts/acf_review_loop.py submit-review --state "$env:TEMP\agent-project-system\REAL-AGENT-REVIEW-LOOP-MVP-001\acceptance-manual-003\state.json" --request "$env:TEMP\agent-project-system\REAL-AGENT-REVIEW-LOOP-MVP-001\acceptance-manual-003\request-r1.json" --artifact-id $r1Sha256
python scripts/acf_review_loop.py render-review-message --state "$env:TEMP\agent-project-system\REAL-AGENT-REVIEW-LOOP-MVP-001\acceptance-manual-003\state.json" --output "$env:TEMP\agent-project-system\REAL-AGENT-REVIEW-LOOP-MVP-001\acceptance-manual-003\r1-browser-relay-packet.txt" --response-presentation COPY_SAFE_PLAIN_TEXT_BLOCK
```

## Round 1 user relay and ingest

Stop and output exactly this instruction followed by the complete, unedited `R1_BROWSER_RELAY_PACKET` file:

```text
USER_ACTION_REQUIRED:
把下面完整的 R1_BROWSER_RELAY_PACKET 复制到 Browser Lead。
Browser Lead 必须把机器 wire 放在一个独立的 copyable plain-text block 中。
请使用该 block 自带的复制按钮，再把完整 RR_REVIEW_BEGIN ... RR_REVIEW_END 原样贴回本对话。
```

The user performs two copy steps: Packet to Browser, then the content obtained from the Browser block's copy control back to the Execution Agent. Do not select ordinary rendered Markdown prose. The copied content must begin with `RR_REVIEW_BEGIN`, end with `RR_REVIEW_END`, contain no fence delimiters, and preserve every top-level field at column zero. Browser should leave one empty line after the final Acceptance Status Evidence before column-zero `FINDINGS:`; this separator is presentation-safe and does not relax parser semantics. Save the returned envelope byte-for-byte as `r1-browser-response.txt`; do not edit, dedent, summarize, wrap, or reconstruct it. Recompute the unchanged R1 hash and ingest:

```powershell
python scripts/acf_review_loop.py ingest-manual-review --state "$env:TEMP\agent-project-system\REAL-AGENT-REVIEW-LOOP-MVP-001\acceptance-manual-003\state.json" --response-file "$env:TEMP\agent-project-system\REAL-AGENT-REVIEW-LOOP-MVP-001\acceptance-manual-003\r1-browser-response.txt" --current-artifact-id $r1Sha256
```

Continue only if Product state proves `REVISION_REQUIRED`, authoritative `REVISE`, nonempty in-scope `REQUIRED_ACTIONS`, and `REVIEW_SOURCE=MANUAL_RELAY`. Any parser, binding, stale, coverage, blocker, or provenance failure is a hard stop. A paraphrase or IDE permission approval is not a Browser Decision.

## Revision, Round 2 user relay, and ingest

Apply exactly the persisted Required Actions. Preserve R1. Create and hash immutable R2 evidence. Set `$revisionEvidence` to a nonempty string identifying the applied action and immutable R2 artifact, then record it:

```powershell
python scripts/acf_review_loop.py revision-applied --state "$env:TEMP\agent-project-system\REAL-AGENT-REVIEW-LOOP-MVP-001\acceptance-manual-003\state.json" --evidence $revisionEvidence
```

Create `request-r2.json` with the same Goal and Gate A criteria, `FINAL`, `READY_FOR_COMPLETION`, and `ROUND_2_REQUEST_ID`. Its `EVIDENCE` must contain concrete values, not a generic summary or placeholder, for every field below:

```text
R1_ARTIFACT_PATH
R1_SHA256
R1_REVIEW_REQUEST_ID
R1_DECISION: REVISE
R1_REVIEW_SOURCE: MANUAL_RELAY
R1_RAW_RESPONSE_SHA256
REQUIRED_ACTION_APPLIED: exact Browser Required Action
R2_ARTIFACT_PATH
R2_SHA256
R2_INPUT.UNRESOLVED_USER_DECISION: "UNVERIFIED"
R2_INPUT.TYPE: string
R2_POLICY_RESULT: exact evaluate_completion_gate result
REVISION_APPLIED_EVIDENCE: exact Evidence persisted by revision-applied
PRODUCT_HEAD
```

Read R1 Decision identity/provenance and revision-applied Evidence from Product state; do not restate them from memory. Read R2 input/result from the immutable R2 artifact. Set `$r2Sha256` to its computed SHA-256, then submit and render:

```powershell
python scripts/acf_review_loop.py submit-review --state "$env:TEMP\agent-project-system\REAL-AGENT-REVIEW-LOOP-MVP-001\acceptance-manual-003\state.json" --request "$env:TEMP\agent-project-system\REAL-AGENT-REVIEW-LOOP-MVP-001\acceptance-manual-003\request-r2.json" --artifact-id $r2Sha256
python scripts/acf_review_loop.py render-review-message --state "$env:TEMP\agent-project-system\REAL-AGENT-REVIEW-LOOP-MVP-001\acceptance-manual-003\state.json" --output "$env:TEMP\agent-project-system\REAL-AGENT-REVIEW-LOOP-MVP-001\acceptance-manual-003\r2-browser-relay-packet.txt" --response-presentation COPY_SAFE_PLAIN_TEXT_BLOCK
```

Stop and output exactly this instruction followed by the complete, unedited `R2_BROWSER_RELAY_PACKET` file:

```text
USER_ACTION_REQUIRED:
把下面完整的 R2_BROWSER_RELAY_PACKET 复制到 Round 1 使用的同一个 Browser Lead Conversation。
Browser Lead 必须把机器 wire 放在一个独立的 copyable plain-text block 中。
请使用该 block 自带的复制按钮，再把完整 RR_REVIEW_BEGIN ... RR_REVIEW_END 原样贴回本对话。
```

The user performs two more copy steps using the Browser block's copy control. Apply the same column-zero, no-fence, blank-line-before-`FINDINGS:` presentation rule. Save the complete response byte-for-byte as `r2-browser-response.txt`; never repair formatting locally. Recompute the unchanged R2 hash and ingest:

```powershell
python scripts/acf_review_loop.py ingest-manual-review --state "$env:TEMP\agent-project-system\REAL-AGENT-REVIEW-LOOP-MVP-001\acceptance-manual-003\state.json" --response-file "$env:TEMP\agent-project-system\REAL-AGENT-REVIEW-LOOP-MVP-001\acceptance-manual-003\r2-browser-response.txt" --current-artifact-id $r2Sha256
```

The ingest command must return authoritative `APPROVE` and `COMPLETED`. Immediately preserve its output, then use the public read-only state command:

```powershell
python scripts/acf_review_loop.py show --state "$env:TEMP\agent-project-system\REAL-AGENT-REVIEW-LOOP-MVP-001\acceptance-manual-003\state.json"
```

## Gate B verification and final report

Verify Gate B only from the saved R2 raw bytes, ingest output, and shown Product state:

1. Recompute `r2-browser-response.txt` SHA-256 and match it to the R2 `MANUAL_REVIEW_INGESTED.RAW_RESPONSE_SHA256` event.
2. Require that event to bind `REVIEW_SOURCE=MANUAL_RELAY`, `ROUND_2_REQUEST_ID`, and `$r2Sha256`.
3. Require `AUTHORITATIVE_REVIEW_DECISION` to be the matching Final `APPROVE`, with exact all-`MET` Gate A coverage, no blockers, no Required Actions, and no unresolved User Decision.
4. Require `WORKFLOW_STATE=COMPLETED`; this is the persisted result of the existing Completion Gate path, not an Execution Agent assertion.
5. Confirm no local or Execution Agent Decision was substituted for either Browser response.
6. Write `final-report.txt` only after checks 1 through 5 pass.

If any check fails, write only the truthful failure evidence and `RUN_RESULT: POST_INGEST_COMPLETION_FAILURE`; do not alter or reinterpret the Browser's historical Decision.

The successful final report must contain:

```text
LOGICAL_TURN_COUNT: AT_LEAST_4
ROUND_1_DECISION: REVISE
ROUND_1_AUTHORITATIVE: YES
ROUND_1_REQUIRED_ACTION_APPLIED: YES
ROUND_2_DECISION: APPROVE
ROUND_2_AUTHORITATIVE: YES
DISTINCT_REQUEST_IDS: YES
SAME_BROWSER_CONVERSATION_USER_CONFIRMED: YES
BOTH_RAW_RESPONSES_PRESERVED: YES
BOTH_DECISIONS_INGESTED: YES
MANUAL_REVIEW_PROVENANCE_RECORDED: YES
GATE_A_BROWSER_FINAL_REVIEW: MET
GATE_B_POST_INGEST_COMPLETION_VERIFICATION: PASS
TRANSPORT_IDENTITY_VERIFIED: NO
SAME_BROWSER_CONVERSATION_MACHINE_VERIFIED: NO
COMPLETION_GATE: COMPLETED
COLLABORATION_MVP_USABLE: YES
REAL_AGENT_REVIEW_LOOP_FUNCTIONALLY_VALIDATED: YES
MANUAL_RELAY_VALIDATED: YES
AUTOMATED_BROWSER_TRANSPORT_VALIDATED: NO
WINDOWS_OPENCLI_LONG_ARGV_BLOCKER: OPEN
```

The same Browser Conversation is user-maintained, not machine-verified. Manual Relay establishes functional collaboration Evidence only.

## Hard boundaries and stop report

- Exactly four user copy steps are allowed: R1 out, R1 back, R2 out, R2 back.
- Do not control Browser, invoke automatic Browser delivery, modify frozen Transport, or fabricate identity flags.
- Do not alter raw responses, runtime state by hand, Product code, Specs, Packet, pointer, or repository files during the run.
- Do not create another Acceptance Packet or retry this run inside this Packet.
- Do not merge, close the Work Item, or claim completion without authoritative Final Browser `APPROVE` and Completion Gate `COMPLETED`.

On any hard stop, preserve the runtime directory and report the exact stage, command/exit, response path, artifact hash, Request ID, parser/binding outcome, Workflow State, whether any Browser Decision was ingested, and why continuation is forbidden. Do not repair Product from inside the Acceptance run.
