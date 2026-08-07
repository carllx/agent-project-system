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
- `scripts/opencli_transport.py`: integrated start-new-and-send, bounded identity recovery, deduplication, compatibility diagnostics, and machine-readable state.

Filled Packets, receipts, transport records, and Handoffs are temporary by default. Keep transport state and raw command output in the system temporary directory, record their paths, exclude credentials and unnecessary private content, and clean them after the loop. Do not depend on an IDE-private scratch directory. Prefer stdin; use a safely created temporary file only when stdin is unsuitable.

## Invocation, Assets, and Handoff

- Use the target Agent platform's Skill selection entry to invoke `research-review-lead` manually when the user requests a Browser Research / Review loop.
- The frontmatter `description` supplies semantic candidate signals, but the platform may not proactively select this Skill without an explicit selection. Do not treat that platform behavior as a project-level installation failure.
- After the Skill is selected, resolve bundled paths relative to this `SKILL.md` and read only the asset required by the current scenario. Use `rr-lead-init.md` for creating the Browser RR Lead conversation, `context-packet.md` for the first Work Item sync, `evidence-packet.md` for verified execution evidence, `decision-request.md` for a genuine user decision gate, and `handoff.md` when continuity or Agent handoff is needed.
- When the user expresses handoff intent (for example, “生成 handoff”, “我要交接了”, or “准备给下一个 Agent”), read `assets/handoff.md` and produce its structured handoff from the current project evidence. Output the Handoff in the conversation by default; write a project file only when the user or target-project rules explicitly require persistence, using the designated project location and avoiding disposable document buildup.
- Do not require a target project to duplicate these Skill invocation or asset-reading rules in `AGENTS.md`.

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
work_item_id
message_id
expected_conversation_mode
pre_send_active_conversation_id
verified_target_conversation_id
actual_delivery_conversation_id
delivery_state
send_attempt_count
recovery_attempt_count
misroute_detected
started_at
stopped_at
stop_reason
```

Never rely on the active browser tab.

## PRECHECK

Run only necessary checks:

```powershell
opencli --version
opencli chatgpt status -f yaml
```

Stop without credential recovery when OpenCLI is missing, Browser Bridge is disconnected, ChatGPT is logged out, or the conversation cannot be read reliably. Never inspect cookies, tokens, API keys, or browser credentials.

Local OpenCLI `1.8.6` help and the Transport Smoke incidents established:

- `history --limit <n> -f json` returns conversation IDs, titles, and URLs;
- `detail <id-or-url> --wait --timeout <seconds> --stable <seconds> -f json` returns roles, text, generation state, and stability;
- `ask --new` can deliver into a conversation that existed before the send, then report a page-navigation error;
- explicit-ID `detail` can recover both observed timed-out conversations and their completed replies;
- `new` is a separate read-class command but reports only `Status`; `status` reports the current URL and `read` reports current-page messages;
- history ordering is not a reliable newest-first contract, and scanning every pre-send conversation is prohibited.

`opencli chatgpt send` exists according to help and appears non-waiting, but its creation, targeting, identity capture, and delivery behavior remain `UNVERIFIED`. Do not use it as the trusted runtime path before Experiment A3 passes. Never use `ask --new` to send a real Work Item from an unknown page state.

## Identify every Browser message

Prepend every sent message with:

```text
WORK_ITEM_ID: <id>
MESSAGE_ID: <work-item>-R<round>-<type>
ROUND: <number>
MESSAGE_TYPE: CONTEXT_PACKET / EVIDENCE_PACKET / DECISION_RECEIPT / HANDOFF
```

Before sending and after any timeout, check `MESSAGE_ID`. `MAX_SEND_ATTEMPTS_PER_MESSAGE=1`: after the first attempt, never resend the same `MESSAGE_ID`, including after `DELIVERY_UNKNOWN`, `MISROUTED_DELIVERY`, or `FAILED`. A new experiment uses a new Work Item ID, Message ID, and Runtime directory.

## Use the delivery state model

```text
DELIVERY_STATE:
NOT_SENT
CREATING_CONVERSATION
VERIFYING_CONVERSATION
SENDING
SENT
DELIVERY_UNKNOWN
MISROUTED_DELIVERY
DELIVERED
RESPONSE_PENDING
RESPONSE_READY
FAILED
```

A CLI timeout moves to `DELIVERY_UNKNOWN`, not automatically to `FAILED`. Recovery searches exact `WORK_ITEM_ID` and `MESSAGE_ID` only. A matching message in the verified new Conversation may become `DELIVERED`, `RESPONSE_PENDING`, or `RESPONSE_READY`.

`MISROUTED_DELIVERY` means the exact message is confirmed delivered into a Conversation that existed before the send and was not the Work Item target. Immediately set the Work Item to `BLOCKED`, record only the wrong Conversation ID and minimal exact-ID evidence, prohibit same-ID resend and further use of that Conversation, and set its response as ineligible for formal RR Lead output. Request repair of the new-conversation creation path. Never promote an old-Conversation hit to `DELIVERED`.

## Create, verify, then send

Use one formal operation for every new-conversation delivery:

```text
send --prepare-new = START_NEW_AND_SEND
  -> PRE_SEND_HISTORY_BASELINE
  -> CREATE_NEW_CONVERSATION
  -> VERIFY_NEW_URL_AND_EMPTY_READ
  -> SEND_ONCE
  -> PARSE_ASK_IDENTITY
  -> POST_SEND_STATUS
  -> BOUNDED_RECOVERY_IF_NEEDED
```

Run it with a fresh Runtime and unique Message ID:

```powershell
$packet | python <skill-dir>/scripts/opencli_transport.py send --prepare-new `
  --work-item-id <id> --message-id <id-R0-CONTEXT> `
  --round 0 --message-type CONTEXT_PACKET
```

Within the same Wrapper process, record the bounded history baseline before `new`; verify the resulting URL is ChatGPT root or `/new`; require the shared read classifier to return `EMPTY`; invoke `ask` once; parse JSON or strict flat YAML identity; and always check post-send status. Only when identity is absent, transport fails, or status conflicts may the same call perform one post-send history diff and at most one exact detail. Never use `ask --new`, never require the user to open `/new`, and never split creation and sending into separate formal experiments. The standalone `prepare-new` command remains only for backward-compatible diagnostics and is not a prerequisite or acceptance step.

Use this transport flow:

```text
PREPARE_MESSAGE
-> CREATE_NEW_CONVERSATION
-> VERIFY_NEW_CONVERSATION
-> SEND_MESSAGE
-> CAPTURE_OR_RECOVER_CONVERSATION_ID
-> POLL_OR_READ_RESPONSE
-> PARSE_RR_REVIEW
```

If `new`, URL verification, or empty-read verification fails, stop before sending with `BLOCKED`; do not ask the user to repair Browser page state manually. Set `send_attempt_count=1` and `message_send_count=1` only at the actual underlying `ask` invocation boundary.

Use the wrapper from the target project without copying it:

```powershell
$packet | python <skill-dir>/scripts/opencli_transport.py send --prepare-new `
  --work-item-id <id> --message-id <id-R0-CONTEXT> `
  --round 0 --message-type CONTEXT_PACKET

python <skill-dir>/scripts/opencli_transport.py recover --state-file <recorded-state-file>
```

For subsequent rounds add `--conversation <recorded-id>`. The wrapper uses one short `ask`, then at most one recovery; it does not repeat `ask`. Accept the real OpenCLI JSON or flat YAML `conversationId`/`conversationUrl` identity returned by `ask`. When `ask` returns no usable identity, recovery executes `POST_SEND_STATUS -> POST_SEND_HISTORY_REFRESH -> NEW_CANDIDATE_DIFF -> EXACT_ID_DETAIL_CHECK`: compare the same bounded recent-history window with the pre-send baseline, exclude every pre-send ID from the new-candidate diff, and use at most one exact detail check. Prefer an ask-reported identity, then the current post-send Conversation, then a unique new history candidate. If the current target is a pre-send Conversation and both exact identifiers match, mark `MISROUTED_DELIVERY`; if no exact two-marker match is found, preserve `DELIVERY_UNKNOWN` and forbid resend. Review the JSON result and recorded raw-output paths. Do not parse an RR response before `RESPONSE_READY`, and never parse one when `official_response_eligible` is false. Bind messages and source as one immutable `ResponseMessageBatch` created from one `detail` command or one `ask` result. Establish `verified_target_conversation_id` before calling `accept_delivery`; never let `accept_delivery` write or replace it. Require `response_batch.conversation_id` to exactly equal that verified target, and never trust a Conversation ID claimed by the response body.

Default adjustable parameters are:

```text
COMMAND_WAIT_SECONDS=15
POLL_INTERVAL_SECONDS=5
TOTAL_RESPONSE_WAIT_SECONDS=30
MAX_SEND_ATTEMPTS_PER_MESSAGE=1
MAX_RECOVERY_ATTEMPTS=1
MAX_DETAIL_CHECKS=1
MAX_EXTERNAL_COMMANDS=9
MAX_EXPERIMENT_SECONDS=60
MAX_BACKGROUND_RESULT_CHECKS=1
MAX_BACKGROUND_WAIT_SECONDS=15
FIXED_SCHEDULE_TIMER_ALLOWED=false
```

Keep each command wait short, impose a total response bound, and never use unlimited technical retries. At the bound, preserve the Conversation ID and Handoff and enter `BLOCKED` or `STALLED` as appropriate.

## Deterministic Bootstrap and Manual Relay

First Browser RR Lead creation must use the deterministic `bootstrap` command. The wrapper reads the two files itself, strips a UTF-8 BOM, normalizes newlines, and rejects invalid UTF-8 or lone surrogates before any send, then assembles `BEGIN_RR_LEAD_INITIALIZATION`/`END_RR_LEAD_INITIALIZATION` followed by `BEGIN_CONTEXT_PACKET`/`END_CONTEXT_PACKET` in that fixed order. Do not hand-concatenate init and context with PowerShell.

```powershell
python <skill-dir>/scripts/opencli_transport.py bootstrap --prepare-new `
  --work-item-id <id> --message-id <id-R0-CONTEXT> `
  --init-file <rr-lead-init.md> --context-file <filled-context-packet.md> `
  --state-file <path>
```

Prefer file inputs (`--init-file`, `--context-file`, `--message-file`) for formal payloads. The same Message ID is sent at most once; the wrapper reuses the existing bounded send and recover flow.

If automatic transport cannot deliver within its recovery budget, the wrapper records `WORK_ITEM_STATE: IN_PROGRESS` and `TRANSPORT_STATE: MANUAL_RELAY_REQUIRED` instead of failing the Work Item. To hand a prepared packet to a human, run:

```powershell
python <skill-dir>/scripts/opencli_transport.py manual-export `
  --work-item-id <id> --message-id <id-R0-CONTEXT> `
  --round 0 --message-type CONTEXT_PACKET --message-file <path> `
  --state-file <path>
```

Paste only the `BEGIN_MESSAGE` ... `END_MESSAGE` body into the Browser RR Lead conversation so the on-wire bytes match the reported SHA-256. After the RR Lead replies in the Browser, recover with `recover --continue-pending --state-file <same-path>`.

A Manual Relay is NOT Browser E2E verification; it only hands a prepared packet to a human. A Local Sub Agent review is only a degraded alternative and never satisfies Browser acceptance.

## Bound recovery and experiments

Recovery saves a bounded pre-send history baseline, performs one send, reads post-send status, refreshes the same bounded history window once, computes IDs absent from the baseline, and performs at most one detail check against the strongest bounded target. Search only exact Work Item ID and Message ID, stop on the first hit, and retain no unrelated conversation body. Never scan all pre-send Conversations, enlarge the candidate limit, or poll repeatedly as a recovery substitute.

Run only one final real end-to-end `send --prepare-new` experiment after local validation. If that experiment cannot return a clear Conversation ID and response within the existing finite budget, stop Transport iteration and mark OpenCLI 1.8.6 as currently unreliable for this route; do not create more A2.1/A2.2 micro-experiments or extend the Work Item through repeated patches.

Every experimental Agent Prompt must state that the Agent must not modify the Skill or wrapper; reset Runtime and retry; resend the same Message ID; send unplanned hello/test probes; read unrelated Browser conversations; repair code; or turn the test into open-ended development. Any violation is `HARD_FAILURE: TEST_PROTOCOL_VIOLATION`; stop immediately and do not use that run to pass A2 or A3.

Before any experimental action, validate every required value. Treat an empty string, `null`, `TODO`, `TBD`, `PLACEHOLDER`, `example.com`, any `<...>` token including `https://chatgpt.com/c/<id>`, and text beginning with or containing `请在这里...` as unresolved. Return `BLOCKED_BEFORE_EXECUTION: REQUIRED_VALUE_UNRESOLVED`, list the affected field names, and execute zero external commands. Never substitute a plausible value or run a status/precheck command to compensate for a missing value.

Count every Shell command, `schedule`, `sleep`, timer, poll, file search, source search, and log search as an experiment action from the start of the run. Do not exclude pre-command discovery. Use these experiment defaults unless the current Work Order explicitly overrides them:

```text
MAX_IDLE_WAIT_SECONDS=0
MAX_SCHEDULE_CALLS=0
MAX_POLL_ATTEMPTS=0
```

A Shell call that returns `exit code`, `stdout`, and `stderr` directly within `COMMAND_WAIT_SECONDS=15` is `SYNCHRONOUS_COMPLETION`. If it is the only authorized command, immediately report and end in the current turn. If the Shell first returns `RUNNING`, `PENDING`, `PROCESS_STILL_ACTIVE`, or `JOB_ID_WITH_INCOMPLETE_RESULT`, classify completion as asynchronous only when the same tool event provides a verifiable process handle or Job ID and names a handle-bound result method. Use that method at most once, wait at most 15 seconds, return as soon as the process completes, and report `BACKGROUND_PROCESS_COMPLETION`; never relabel it as synchronous. Without both the handle and its result method, return `EXECUTOR_RESULT: ASYNC_UNSUPPORTED_FOR_CONTROLLED_EXPERIMENT` before running a command expected to exceed the foreground limit.

Treat `schedule`, sleep, a timer, notification waiting, and any wait not bound to the returned process as `IDLE_TIMER_WAIT`. Default-prohibit it even when a Work Order permits a real background-result check. Never use a fixed 300-second schedule as command-result retrieval. Record who initiated every schedule only from the tool event provenance: `MODEL_INITIATED`, `PLATFORM_REQUIRED`, `PLATFORM_AUTO_INSERTED`, or `UNKNOWN`; do not infer platform behavior from an Agent explanation.

Classify placeholder execution as `HARD_FAILURE: TEST_PROTOCOL_VIOLATION` with `UNRESOLVED_PLACEHOLDER_EXECUTION`; classify `IDLE_TIMER_WAIT`, an unbound result read, a second background-result check, or a background wait over 15 seconds as `UNAUTHORIZED_IDLE_WAIT` and a protocol violation. Never end an experiment report with `standing by`, `waiting for timer`, `I will report later`, or `等待下一次状态检测`; provide the final result in the current turn.

Every experiment report must include:

```text
PLACEHOLDER_VALIDATION_PERFORMED
UNRESOLVED_PLACEHOLDERS
WRAPPER_SCHEDULE_CALL_COUNT
AGENT_SCHEDULE_CALL_COUNT
TOTAL_SCHEDULE_CALL_COUNT
AGENT_TOOL_TRACE_VERIFICATION
AGENT_BOUND_RESULT_RETRIEVAL_COUNT
WHO_INITIATED_SCHEDULE
IDLE_WAIT_SECONDS
POLL_ATTEMPT_COUNT
BACKGROUND_RESULT_CHECK_COUNT
BACKGROUND_WAIT_SECONDS
BACKGROUND_PROCESS_HANDLE_SUPPORT
SUPPORTED_WAIT_OR_RESULT_METHOD
COMPLETION_MODE
SYNCHRONOUS_COMMAND_COMPLETED
TERMINATED_IMMEDIATELY_AFTER_RESULT
TEST_PROTOCOL_VIOLATION
TEST_RESULT
REPORT_VALIDATION
EXPERIMENT_ACCEPTANCE
```

Set `WRAPPER_SCHEDULE_CALL_COUNT` only from Wrapper-owned actions. The experiment Agent must fill `AGENT_SCHEDULE_CALL_COUNT` and `AGENT_BOUND_RESULT_RETRIEVAL_COUNT` from its visible tool trace; `TOTAL_SCHEDULE_CALL_COUNT` is their sum. When that trace cannot be counted reliably, report `AGENT_TOOL_TRACE_VERIFICATION=UNAVAILABLE` and leave Agent and total counts unknown—never substitute Wrapper zero for the whole experiment. Also report the external-command count, total experiment-action count, per-action counts, and schedule initiator so discovery and waiting cannot disappear from the evidence. Enforce these report invariants: a visible schedule tool call requires `AGENT_SCHEDULE_CALL_COUNT >= 1`; any positive Agent schedule count requires `TEST_PROTOCOL_VIOLATION=true`; a protocol violation forbids both `TEST_RESULT=PASS` and `EXPERIMENT_ACCEPTANCE=MET`; a schedule call cannot report zero idle-wait time; a completed command with `SYNCHRONOUS_COMMAND_COMPLETED=false` must identify a real handle-bound `BACKGROUND_PROCESS_COMPLETION`; and Wrapper `DELIVERY_UNKNOWN` forbids reuse of the same Message ID. Return `REPORT_VALIDATION_FAILED` when any report fields conflict.

Transport A2 and A3 must both pass before the formal Loop starts. The formal Loop must contain at least two complete `IDE execution -> Evidence Packet -> RR Lead review` cycles, and may return `ACHIEVED` only when every original acceptance criterion is `MET`.

## Parse review and execute work

Require an actual Browser response containing:

```text
RR_REVIEW_BEGIN
WORK_ITEM_ID
IN_REPLY_TO_MESSAGE_ID
ROUND
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
RR_REVIEW_END
```

Require the first non-empty line to be exactly `RR_REVIEW_BEGIN` and the last non-empty line to be exactly `RR_REVIEW_END`; reject missing markers and any leading or trailing explanation, example, quotation, or other text. Parse required fields only inside the envelope, reject duplicates, and require `WORK_ITEM_ID`, `IN_REPLY_TO_MESSAGE_ID`, and `ROUND` to exactly equal the current Work Item, the last sent full Message ID, and the expected round. In the verified Conversation, collect user-role messages with exact `WORK_ITEM_ID` and `MESSAGE_ID`: reject zero matches, return `OUTBOUND_MESSAGE_IDENTITY_AMBIGUOUS` for multiple matches without selecting an anchor or entering the formal parser, and only for one match inspect assistant-role messages after it. Never parse a user quotation, an earlier Assistant reply, or content from another Conversation. Accept exactly one complete identity-matching response as `RESPONSE_IDENTITY_VERIFIED`; return `RESPONSE_IDENTITY_MISSING`, `RESPONSE_IDENTITY_MISMATCH`, `RESPONSE_IDENTITY_AMBIGUOUS`, `RESPONSE_SOURCE_CONVERSATION_MISMATCH`, or `RESPONSE_PENDING` otherwise. Reject incomplete output, never fill missing fields locally, never pass identity failures to the formal Review Parser, and never resend the same Message ID after an identity failure. Execute `NEXT_WORK_ORDER` only for `IN_PROGRESS`, inside user authorization and project rules, with no pending decision. Build the next Evidence Packet from actual artifacts, commands, tests, observations, sources, failures, and acceptance mapping. Git evidence is conditional on Git being used.

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
