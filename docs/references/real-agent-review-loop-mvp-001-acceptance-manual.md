# Real Agent Review Loop Manual Relay Acceptance Contract

PACKET_TYPE: REAL_AGENT_REVIEW_LOOP_MANUAL_RELAY_PACKET

PACKET_STATE: READY_NOT_STARTED

MANUAL_RELAY_ACCEPTANCE_READY: YES

WORK_ITEM_ID: REAL-AGENT-REVIEW-LOOP-MVP-001

ACCEPTANCE_RUN_ID: REAL-AGENT-REVIEW-LOOP-MVP-001-ACCEPTANCE-MANUAL

TRANSPORT_MODE: MANUAL_RELAY

REQUIRED_PRODUCT_HEAD: 0f496665ebcd85154cac6ffc83b9e80b62a3e31f

PRODUCT_ROOT: E:\PROJECTS\agent-project-system

RUNTIME_ROOT: %TEMP%\agent-project-system\REAL-AGENT-REVIEW-LOOP-MVP-001\acceptance-manual

ROUND_1_REQUEST_ID: REAL-AGENT-REVIEW-LOOP-MVP-001-ACCEPTANCE-MANUAL-R1-FINAL

ROUND_2_REQUEST_ID: REAL-AGENT-REVIEW-LOOP-MVP-001-ACCEPTANCE-MANUAL-R2-FINAL

## Authority and start gate

This Packet is prepared, not started. A fresh Execution Agent may begin only after the user or Browser Lead explicitly starts this Acceptance Run. Read `AGENTS.md`, `README.md`, `docs/index.md`, `docs/current.md`, the active pointer, this Packet, and the applicable ACF/RR Specs. Historical conversations and Agent memory are not execution authority.

Before creating runtime artifacts:

1. Confirm this is the active Packet and its state is `READY_NOT_STARTED`.
2. Confirm branch `work/real-agent-review-loop-mvp-001`, a clean worktree, local HEAD equal to the remote tracking ref, and `REQUIRED_PRODUCT_HEAD` an ancestor of HEAD.
3. Confirm `RUNTIME_ROOT` does not exist. Never reuse an earlier state, Request ID, response, or artifact.
4. Use repository source as Product authority.
5. Stop as `ACTIVE_EXECUTION_PACKET_INVALID` on any mismatch.

## Goal and acceptance criteria

Run one real four-turn minimum collaboration loop:

```text
Turn 1: Execution Agent executes the evidence task and submits Final R1
Turn 2: independent Browser Lead returns authoritative REVISE
Turn 3: Execution Agent applies REQUIRED_ACTIONS and submits Final R2
Turn 4: the same Browser Lead Conversation returns authoritative APPROVE
```

The real task is to execute the Product Completion-Gate policy and preserve immutable, repository-external observations. R1 records the base-state policy result. The Browser must identify a concrete evidence deficiency and return an executable in-scope revision. The expected bounded revision is a new immutable R2 observation that preserves R1 and adds the policy result for string-valued `UNRESOLVED_USER_DECISION="UNVERIFIED"`. Do not hand-author policy results.

Agreed Acceptance Criteria:

1. `AC1`: a real Antigravity Execution Agent performs the evidence task; Browser decisions are not simulated locally.
2. `AC2`: R1 is relayed once and strictly ingested as authoritative `REVISE` with executable Required Actions.
3. `AC3`: the persisted Required Actions are actually applied and evidenced in a new immutable artifact.
4. `AC4`: R2 uses a new Request ID, the same `FINAL` Review Kind, and the same user-maintained Browser Lead Conversation.
5. `AC5`: R2 is relayed once and strictly ingested as authoritative `APPROVE` with exact all-`MET` coverage.
6. `AC6`: both raw Browser responses are preserved byte-for-byte and their Manual Relay provenance is recorded.
7. `AC7`: neither Execution Agent nor a Product label self-approves completion.
8. `AC8`: Completion Gate reaches `COMPLETED` only after the current matching Final approval.

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
python scripts/acf_review_loop.py initialize --contract "$env:TEMP\agent-project-system\REAL-AGENT-REVIEW-LOOP-MVP-001\acceptance-manual\contract.json" --state "$env:TEMP\agent-project-system\REAL-AGENT-REVIEW-LOOP-MVP-001\acceptance-manual\state.json"
```

Execute `runtime.completion_gate.base_state()` and `evaluate_completion_gate()` from repository source. Save the exact input and result as immutable R1 JSON and calculate its lowercase SHA-256. Create `request-r1.json` with the exact Goal/criteria snapshot and:

```text
PROTOCOL_VERSION: ACF-0.1
WORK_ITEM_ID: REAL-AGENT-REVIEW-LOOP-MVP-001
REVIEW_REQUEST_ID: REAL-AGENT-REVIEW-LOOP-MVP-001-ACCEPTANCE-MANUAL-R1-FINAL
REVIEW_KIND: FINAL
REVIEW_TRIGGER: READY_FOR_COMPLETION
CURRENT_TASK: Independently review the R1 Completion-Gate observation and Manual Relay loop evidence.
CHANGES: repository-external immutable R1 observation only
EVIDENCE: exact R1 path, SHA-256, Product head, and local checks
EXECUTION_ASSESSMENT.CLAIMED_STATUS: CLAIM_READY_FOR_REVIEW
```

Set `$r1Sha256` to the computed R1 artifact SHA-256. Submit and render R1:

```powershell
python scripts/acf_review_loop.py submit-review --state "$env:TEMP\agent-project-system\REAL-AGENT-REVIEW-LOOP-MVP-001\acceptance-manual\state.json" --request "$env:TEMP\agent-project-system\REAL-AGENT-REVIEW-LOOP-MVP-001\acceptance-manual\request-r1.json" --artifact-id $r1Sha256
python scripts/acf_review_loop.py render-review-message --state "$env:TEMP\agent-project-system\REAL-AGENT-REVIEW-LOOP-MVP-001\acceptance-manual\state.json" --output "$env:TEMP\agent-project-system\REAL-AGENT-REVIEW-LOOP-MVP-001\acceptance-manual\r1-browser-relay-packet.txt"
```

## Round 1 user relay and ingest

Stop and output exactly this instruction followed by the complete, unedited `R1_BROWSER_RELAY_PACKET` file:

```text
USER_ACTION_REQUIRED:
把下面完整的 R1_BROWSER_RELAY_PACKET 复制到 Browser Lead。
然后把 Browser Lead 返回的完整 RR_REVIEW_BEGIN ... RR_REVIEW_END 原样贴回本对话。
```

The user performs two copy steps: Packet to Browser, then raw response back. Save the returned envelope byte-for-byte as `r1-browser-response.txt`; do not edit, summarize, wrap, or reconstruct it. Recompute the unchanged R1 hash and ingest:

```powershell
python scripts/acf_review_loop.py ingest-manual-review --state "$env:TEMP\agent-project-system\REAL-AGENT-REVIEW-LOOP-MVP-001\acceptance-manual\state.json" --response-file "$env:TEMP\agent-project-system\REAL-AGENT-REVIEW-LOOP-MVP-001\acceptance-manual\r1-browser-response.txt" --current-artifact-id $r1Sha256
```

Continue only if Product state proves `REVISION_REQUIRED`, authoritative `REVISE`, nonempty in-scope `REQUIRED_ACTIONS`, and `REVIEW_SOURCE=MANUAL_RELAY`. Any parser, binding, stale, coverage, blocker, or provenance failure is a hard stop. A paraphrase or IDE permission approval is not a Browser Decision.

## Revision, Round 2 user relay, and ingest

Apply exactly the persisted Required Actions. Preserve R1. Create and hash immutable R2 evidence. Set `$revisionEvidence` to a nonempty string identifying the applied action and immutable R2 artifact, then record it:

```powershell
python scripts/acf_review_loop.py revision-applied --state "$env:TEMP\agent-project-system\REAL-AGENT-REVIEW-LOOP-MVP-001\acceptance-manual\state.json" --evidence $revisionEvidence
```

Create `request-r2.json` with the same Goal and criteria, `FINAL`, `READY_FOR_COMPLETION`, `ROUND_2_REQUEST_ID`, the exact R1 Decision binding, the applied-action evidence, and both artifact paths/hashes. Set `$r2Sha256` to the computed R2 artifact SHA-256, then submit and render:

```powershell
python scripts/acf_review_loop.py submit-review --state "$env:TEMP\agent-project-system\REAL-AGENT-REVIEW-LOOP-MVP-001\acceptance-manual\state.json" --request "$env:TEMP\agent-project-system\REAL-AGENT-REVIEW-LOOP-MVP-001\acceptance-manual\request-r2.json" --artifact-id $r2Sha256
python scripts/acf_review_loop.py render-review-message --state "$env:TEMP\agent-project-system\REAL-AGENT-REVIEW-LOOP-MVP-001\acceptance-manual\state.json" --output "$env:TEMP\agent-project-system\REAL-AGENT-REVIEW-LOOP-MVP-001\acceptance-manual\r2-browser-relay-packet.txt"
```

Stop and output exactly this instruction followed by the complete, unedited `R2_BROWSER_RELAY_PACKET` file:

```text
USER_ACTION_REQUIRED:
把下面完整的 R2_BROWSER_RELAY_PACKET 复制到 Round 1 使用的同一个 Browser Lead Conversation。
然后把 Browser Lead 返回的完整 RR_REVIEW_BEGIN ... RR_REVIEW_END 原样贴回本对话。
```

The user performs two more copy steps. Save the complete response byte-for-byte as `r2-browser-response.txt`; recompute the unchanged R2 hash and ingest:

```powershell
python scripts/acf_review_loop.py ingest-manual-review --state "$env:TEMP\agent-project-system\REAL-AGENT-REVIEW-LOOP-MVP-001\acceptance-manual\state.json" --response-file "$env:TEMP\agent-project-system\REAL-AGENT-REVIEW-LOOP-MVP-001\acceptance-manual\r2-browser-response.txt" --current-artifact-id $r2Sha256
```

Only authoritative `APPROVE`, exact all-`MET` coverage with evidence, no blockers, no Required Actions, no unresolved User Decision, current artifact identity, and Completion Gate `COMPLETED` pass.

## Required final evidence

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
