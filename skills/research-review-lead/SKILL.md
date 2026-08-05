---
name: research-review-lead
description: Drive a real, recoverable Work Item loop between an IDE-side execution agent and an independent Browser RR Lead in ChatGPT through OpenCLI. Use when work needs evidence-based review, explicit next work orders, shared acceptance criteria, bounded transport recovery, user decision pauses, or handoff across code, teaching, document, research, and non-Git projects.
---

# Research Review Lead Loop Driver

## Keep the roles separate

- **Builder IDE Agent:** maintain this Skill in its source repository.
- **IDE-side Loop Driver:** run the Skill in a target project, execute authorized work, exchange Packets through OpenCLI, and maintain loop and delivery state.
- **Browser RR Lead:** exist in a real ChatGPT browser conversation; research, review evidence, judge the shared acceptance criteria, and issue the next work order.
- **User:** decide goals, value, cost, accounts, permissions, privacy, publication, irreversible actions, major risk, and material downgrade.

The IDE-side Loop Driver must never impersonate the Browser RR Lead or manufacture a browser-style review. A prepared Packet is not a delivered message, and a local judgment is not a Browser RR Lead response.

Use **Full Governance Mode** when the target project has `AGENTS.md`, a current-state authority, or equivalent entry points. Otherwise use **Compatibility Mode** and derive the Work Item from the user request and existing artifacts. Do not require Git; when Git is not used, report that Git evidence is not applicable.

## Load package resources

Resolve these paths relative to this `SKILL.md`:

- `assets/rr-lead-init.md`: Browser RR Lead rules;
- `assets/context-packet.md`: initial Goal Contract and context;
- `assets/evidence-packet.md`: verified execution evidence;
- `assets/decision-request.md`: genuine user decision gate;
- `assets/handoff.md`: continuity handoff;
- `scripts/opencli_transport.py`: bounded send, identity recovery, deduplication, polling, and machine-readable state.

Filled Packets, receipts, transport records, and Handoffs are temporary by default. Keep transport state and raw command output in the system temporary directory, record their paths, exclude credentials and unnecessary private content, and clean them after the loop. Do not depend on an IDE-private scratch directory. Prefer stdin; use a safely created temporary file only when stdin is unsuitable.

## Establish one Goal Contract

Create one authoritative contract in the Context Packet:

```text
WORK_ITEM_ID
SHARED_OBJECTIVE
ACCEPTANCE_CRITERIA
SCOPE
CONSTRAINTS
EVIDENCE_REQUIRED
STOP_CONDITIONS
```

Use this unchanged contract for Browser review unless the user explicitly changes it. New non-blocking findings go to `DEBT`; the Browser RR Lead must not silently add pass conditions outside `ACCEPTANCE_CRITERIA`.

## Run the goal loop

```text
COMMON_GOAL
-> IDE_EXECUTION
-> IDE_EVIDENCE
-> RR_ACCEPTANCE_REVIEW
-> FIX_AND_RESUBMIT_IF_NEEDED
-> ACHIEVED_WHEN_ALL_CRITERIA_MET
```

Continue only while `WORK_ITEM_STATE: IN_PROGRESS`, an executable `NEXT_WORK_ORDER` exists, no decision or safety gate is active, and new evidence or a reasonable new path exists. Stop at `ACHIEVED`, `BLOCKED`, `NEEDS_DECISION`, `STALLED`, or `UNSAFE`. Do not describe or implement this as an infinite loop.

Maintain:

```text
WORK_ITEM_ID
CONVERSATION_ID_OR_URL
CURRENT_ROUND
LAST_SUCCESSFUL_READ_AT
LAST_SUCCESSFUL_WRITE_AT
CURRENT_STATE
DELIVERY_STATE
LAST_MESSAGE_ID
```

Never rely on the active browser tab.

## PRECHECK

Run only necessary checks:

```powershell
opencli --version
opencli chatgpt status -f yaml
```

Stop without credential recovery when OpenCLI is missing, Browser Bridge is disconnected, ChatGPT is logged out, or the conversation cannot be read reliably. Never inspect cookies, tokens, API keys, or browser credentials.

Local OpenCLI `1.8.6` help and the `TRANSPORT-SMOKE-001` incident established:

- `history --limit <n> -f json` returns conversation IDs, titles, and URLs;
- `detail <id-or-url> --wait --timeout <seconds> --stable <seconds> -f json` returns roles, text, generation state, and stability;
- `ask --new` can create and deliver a message even when the CLI later times out without returning identity;
- explicit-ID `detail` can recover both observed timed-out conversations and their completed replies;
- history ordering is not a reliable newest-first contract, so compare pre-send and post-send ID sets rather than selecting the first row.

`opencli chatgpt send` exists according to help and appears non-waiting, but its creation, targeting, identity capture, and delivery behavior remain `UNVERIFIED`. Do not use it as the trusted runtime path before a separate no-side-effect Transport Smoke Test.

## Identify every Browser message

Prepend every sent message with:

```text
WORK_ITEM_ID: <id>
MESSAGE_ID: <work-item>-R<round>-<type>
ROUND: <number>
MESSAGE_TYPE: CONTEXT_PACKET / EVIDENCE_PACKET / DECISION_RECEIPT / HANDOFF
```

Before sending and after any timeout, check `MESSAGE_ID`. Never resend the same `MESSAGE_ID` while its state is `SENDING`, `SENT`, `DELIVERY_UNKNOWN`, `DELIVERED`, `RESPONSE_PENDING`, or `RESPONSE_READY`. A new attempt requires confirmed failure and a new user-authorized recovery plan; ordinary timeout is not confirmed failure.

## Use the delivery state model

```text
DELIVERY_STATE:
NOT_SENT
SENDING
SENT
DELIVERY_UNKNOWN
DELIVERED
RESPONSE_PENDING
RESPONSE_READY
FAILED
```

A CLI timeout moves to `DELIVERY_UNKNOWN`, not automatically to `FAILED`. Run history/detail recovery. A found matching message is `DELIVERED`; if its response is incomplete, use `RESPONSE_PENDING`; when the assistant text is non-empty, `Generating` is false, and the reported stability reaches the configured threshold, use `RESPONSE_READY`. Use `FAILED` only after evidence confirms no conversation/message was created or the transport returned a terminal error and recovery confirms absence. If bounded recovery cannot establish delivery either way, preserve state and enter Work Item `BLOCKED` or `STALLED` rather than resending.

## Split sending from reading

Use this transport flow:

```text
PREPARE_MESSAGE
-> SEND_ONCE
-> CAPTURE_OR_RECOVER_CONVERSATION_ID
-> POLL_OR_READ_RESPONSE
-> PARSE_RR_REVIEW
```

Use the wrapper from the target project without copying it:

```powershell
$packet | python <skill-dir>/scripts/opencli_transport.py send `
  --work-item-id <id> --message-id <id-R0-CONTEXT> `
  --round 0 --message-type CONTEXT_PACKET

python <skill-dir>/scripts/opencli_transport.py recover --state-file <recorded-state-file>
```

For subsequent rounds add `--conversation <recorded-id-or-url>`. The wrapper uses one short `ask`, then switches to recovery and polling; it does not repeat `ask`. Review its JSON result and recorded raw-output paths. Do not parse an RR response before `RESPONSE_READY`.

Default adjustable parameters are:

```text
COMMAND_WAIT_SECONDS=25
POLL_INTERVAL_SECONDS=5
TOTAL_RESPONSE_WAIT_SECONDS=120
MAX_RECOVERY_ATTEMPTS=3
```

Keep each command wait short, impose a total response bound, and never use unlimited technical retries. At the bound, preserve the Conversation ID and Handoff and enter `BLOCKED` or `STALLED` as appropriate.

## Parse review and execute work

Require an actual Browser response containing:

```text
WORK_ITEM_ID
REVIEW_DECISION: PASS / PASS_WITH_DEBT / REVISE / ESCALATE
WORK_ITEM_STATE: IN_PROGRESS / ACHIEVED / BLOCKED / NEEDS_DECISION / STALLED / UNSAFE
ACCEPTANCE_STATUS
  - Criterion
  - Status: MET / NOT_MET / UNVERIFIED
  - Evidence
FINDINGS
BLOCKERS
DEBT
NEXT_WORK_ORDER
VALIDATION
USER_DECISION_REQUIRED
```

Reject incomplete output; never fill missing fields locally. Execute `NEXT_WORK_ORDER` only for `IN_PROGRESS`, inside user authorization and project rules, with no pending decision. Build the next Evidence Packet from actual artifacts, commands, tests, observations, sources, failures, and acceptance mapping. Git evidence is conditional on Git being used.

## Human-in-the-loop

When the Browser RR Lead returns `NEEDS_DECISION`:

1. Stop execution and do not choose for the user.
2. Confirm the Browser response gives three plain-language options, their effects, and one recommendation.
3. Ask the user to decide in that Browser conversation; do not poll automatically.
4. After the user says they answered, recover the same explicit Conversation ID or URL.
5. Verify the Work Item and decision, generate a Decision Receipt, then resume only the selected path.

## Stop, recover, and stay safe

- `ACHIEVED`: all shared acceptance criteria are `MET`; summarize evidence.
- `BLOCKED`: identify the missing external condition and preserve recovery state.
- `STALLED`: stop after bounded, non-duplicating attempts and generate a Handoff.
- `UNSAFE`: stop immediately.
- `NEEDS_DECISION`: follow the procedure above.

The sixth round is a health checkpoint for drift, repetition, missing evidence, and conversation reliability, not a forced stop.

Do not read unrelated conversations or private files; save credentials; upload, publish, pay, change account permissions, or perform irreversible actions without authorization; or run `git add`, `git stash`, commit, or push by default. The Browser RR Lead reviews and directs but does not directly control the IDE.
