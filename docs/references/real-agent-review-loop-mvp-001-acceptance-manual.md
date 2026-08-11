# Real Agent Review Loop Manual Relay Acceptance Contract

PACKET_TYPE: REAL_AGENT_REVIEW_LOOP_MANUAL_RELAY_PACKET

PACKET_STATE: BLOCKED_NOT_READY

MANUAL_RELAY_ACCEPTANCE_READY: NO

WORK_ITEM_ID: REAL-AGENT-REVIEW-LOOP-MVP-001

ACCEPTANCE_RUN_ID: REAL-AGENT-REVIEW-LOOP-MVP-001-ACCEPTANCE-MANUAL

TRANSPORT_MODE: MANUAL_RELAY

REQUIRED_PRODUCT_HEAD: 7eead49dec3421c1aa7f6fb21be90091454754e4

PRODUCT_ROOT: E:\PROJECTS\agent-project-system

RUNTIME_ROOT: %TEMP%\agent-project-system\REAL-AGENT-REVIEW-LOOP-MVP-001\acceptance-manual

ROUND_1_REQUEST_ID: REAL-AGENT-REVIEW-LOOP-MVP-001-ACCEPTANCE-MANUAL-R1-FINAL

ROUND_2_REQUEST_ID: REAL-AGENT-REVIEW-LOOP-MVP-001-ACCEPTANCE-MANUAL-R2-FINAL

BLOCKER: MANUAL_RELAY_RESPONSE_INGEST_ADAPTER_MISSING

## Current authority state

This is the only current Manual Relay Acceptance Contract, but it is intentionally fail-closed and must not be started. Browser Lead rejected the previous document because it retained automatic Transport commands and contradicted `TRANSPORT_MODE: MANUAL_RELAY`.

The existing Product can initialize Loop state, submit a Review Request, and render the canonical Browser Review body without Browser automation. It cannot yet take a user-relayed raw Browser response, strictly parse and bind it, then persist the authoritative transition through the Product driver. No Agent may fill that gap with an invented command, a hand-built Transport state, direct internal-function invocation, or a locally fabricated Decision.

Stop at bootstrap with:

```text
MANUAL_RELAY_ACCEPTANCE_READY: NO
STOP_REASON: MANUAL_RELAY_RESPONSE_INGEST_ADAPTER_MISSING
USER_ACTION_REQUIRED: NONE UNTIL PRODUCT CHANGE IS AUTHORIZED
```

## Intended collaboration flow

Once the missing adapter is separately authorized, implemented, reviewed, and this Packet is changed to `READY_NOT_STARTED`, the exact human collaboration flow is:

```text
Antigravity executes R1 task and produces canonical R1 relay body
→ user copies R1_BROWSER_RELAY_PACKET into the current Browser Lead Conversation
→ Browser Lead returns complete RR_REVIEW with authoritative REVISE
→ user copies the complete response back to Antigravity
→ Product Manual Relay adapter saves, validates, and ingests R1
→ Antigravity applies only REQUIRED_ACTIONS and creates immutable R2 evidence
→ user copies R2_BROWSER_RELAY_PACKET into the same Browser Lead Conversation
→ Browser Lead returns complete RR_REVIEW with authoritative APPROVE
→ user copies the complete response back to Antigravity
→ Product Manual Relay adapter saves, validates, and ingests R2
→ Completion Gate permits COMPLETED
```

Manual Relay validates the collaboration loop, not automated Browser delivery.

## Goal and acceptance semantics

The future run must prove a real `Execute → Review → REVISE → Revision → Review → APPROVE → Completion Gate` loop with an independent Browser Lead. Execution Agent cannot self-approve, cannot infer missing response fields, and cannot complete from an IDE permission approval, natural stop, Transport label, or user paraphrase.

Successful Manual Relay output must be:

```text
COLLABORATION_MVP_USABLE: YES
REAL_AGENT_REVIEW_LOOP_FUNCTIONALLY_VALIDATED: YES
MANUAL_RELAY_VALIDATED: YES
AUTOMATED_BROWSER_TRANSPORT_VALIDATED: NO
WINDOWS_OPENCLI_LONG_ARGV_BLOCKER: OPEN
```

## Outbound capability already available

After future readiness authorization, Round 1 outbound generation will use only the Product state driver:

1. Create the exact runtime `contract.json`, immutable R1 observation, SHA-256 artifact identity, and `request-r1.json`.
2. Run `initialize` once against a new runtime state.
3. Run `submit-review` with `ROUND_1_REQUEST_ID` and the immutable R1 artifact identity.
4. Run `render-review-message` once to create the immutable `R1_BROWSER_RELAY_PACKET` file.
5. Stop and show the user:

```text
USER_ACTION_REQUIRED:
Copy the complete R1_BROWSER_RELAY_PACKET into the current Browser Lead Conversation.
Then copy the Browser Lead's complete RR_REVIEW response back without editing, summarizing, or reformatting it.
```

The Agent does not open or control Browser. The user is responsible for using the intended Browser Lead Conversation.

## Round 1 response requirement

The user-relayed response must be saved byte-for-byte as an immutable `r1-browser-response.txt` artifact before validation. The missing Product adapter must then:

1. require exactly one complete `RR_REVIEW_BEGIN` through `RR_REVIEW_END` envelope with no leading or trailing content;
2. reject missing, duplicate, malformed, or unknown required fields;
3. bind `PROTOCOL_VERSION=ACF-0.1`, this Work Item, `ROUND_1_REQUEST_ID`, and `REVIEW_KIND=FINAL`;
4. validate exact Acceptance Criterion coverage and nonempty Evidence;
5. derive reviewed-state currency from the local artifact identity;
6. persist the transition only through the existing Review Loop;
7. return `NON_AUTHORITATIVE` without state transition on any mismatch.

Only authoritative `REVISE` with nonempty in-scope `REQUIRED_ACTIONS` may enter `REVISION_REQUIRED`. No current Product command performs these steps for a raw response; therefore execution must not proceed.

## Revision and Round 2 requirements

After the future adapter authoritatively ingests R1, the Execution Agent must apply exactly the persisted Required Actions, create a new immutable R2 artifact, preserve R1, record revision Evidence, and submit a new Final Review Request using `ROUND_2_REQUEST_ID`.

The Product renderer must create immutable `R2_BROWSER_RELAY_PACKET`. The Agent must stop again and show the user:

```text
USER_ACTION_REQUIRED:
Copy the complete R2_BROWSER_RELAY_PACKET into the same Browser Lead Conversation used for Round 1.
Then copy the Browser Lead's complete RR_REVIEW response back without editing, summarizing, or reformatting it.
```

The returned response must be saved byte-for-byte as immutable `r2-browser-response.txt` and pass the same strict adapter validation, bound to `ROUND_2_REQUEST_ID` and `FINAL`. Only authoritative `APPROVE`, exact all-`MET` coverage, no blockers, no Required Actions, no unresolved User Decision, and current artifact identity may reach Completion Gate.

## Required final gate

The future run passes only if persisted Product state and immutable artifacts prove:

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
COMPLETION_GATE: COMPLETED
COLLABORATION_MVP_USABLE: YES
REAL_AGENT_REVIEW_LOOP_FUNCTIONALLY_VALIDATED: YES
MANUAL_RELAY_VALIDATED: YES
AUTOMATED_BROWSER_TRANSPORT_VALIDATED: NO
WINDOWS_OPENCLI_LONG_ARGV_BLOCKER: OPEN
```

## Hard boundaries

- Do not start this Acceptance while `PACKET_STATE=BLOCKED_NOT_READY`.
- Do not use Browser automation or any automatic Browser Transport command.
- Do not modify Product state files or synthesize a verified response artifact by hand.
- Do not invoke internal Review Loop functions as a substitute for a formal Product adapter.
- Do not create another Acceptance Packet or retry run.
- Do not modify Product, Transport, Completion Gate, Stop Hook, pointer, or governance from an Execution Agent.
- Do not merge, close the Work Item, or claim completion without authoritative Final Browser `APPROVE` and Completion Gate `COMPLETED`.

## Readiness exit criterion

Browser Lead or the user must separately authorize the minimum Product change. After implementation, tests must prove raw response preservation, strict envelope parsing, exact ACF binding, malformed/mismatched fail-closed behavior, R1 `REVISE`, R2 `APPROVE`, stale approval rejection, and Completion Gate integration. Only a reviewed follow-up may change this Packet and pointer to `READY_NOT_STARTED`.
