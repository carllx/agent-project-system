---
name: research-review-lead
description: Drive a real Work Item loop between an IDE-side execution agent and an independent Browser RR Lead in ChatGPT through OpenCLI. Use when work needs external research, evidence-based review, explicit NEXT_WORK_ORDER execution, user decision pauses, conversation recovery, or handoff across code, product, teaching, document, research, and non-Git projects.
---

# Research Review Lead Loop Driver

## Keep the roles separate

- **Builder IDE Agent:** maintain this Skill in its source repository. Do not participate in a target project's runtime loop merely because you are editing the package.
- **IDE-side Loop Driver:** load this Skill in the target project, read local facts, build Packets, call OpenCLI, parse the Browser RR Lead response, execute authorized `NEXT_WORK_ORDER` steps, and maintain loop state.
- **Browser RR Lead:** exist in a real ChatGPT browser conversation. Perform user communication, necessary external research, technical review, state judgment, and next-step direction.
- **User:** decide goals, value, cost, accounts, permissions, privacy, uploads, irreversible actions, major risk, and material downgrade.

The IDE-side Loop Driver must never impersonate the Browser RR Lead or manufacture a review that merely looks browser-authored. A prepared Packet is not a sent message; a local opinion is not a Browser RR Lead response.

## Select project governance

Use **Full Governance Mode** when the target project has `AGENTS.md`, a current-state source, or equivalent authority entry points. Read and obey them, use their validation methods, and do not copy or replace project governance.

Use **Compatibility Mode** otherwise. Derive the Work Item from the user request and existing entry points. Do not require Git, `docs/current.md`, or governance initialization. Governance may be suggested later but is not a condition for completing the current task.

## Load the package assets

Resolve these paths relative to this `SKILL.md`:

- `assets/rr-lead-init.md`: initialization rules to send to the Browser RR Lead;
- `assets/context-packet.md`: first Work Item synchronization;
- `assets/evidence-packet.md`: verified execution or research evidence;
- `assets/decision-request.md`: a genuine user decision gate;
- `assets/handoff.md`: loop or conversation continuity failure.

Filled Packets, receipts, and Handoffs are temporary messages by default. Do not add them to the target project unless the user or project rules require it.

## Run the state machine

Follow this exact control flow:

```text
PRECHECK
-> CREATE_OR_RESUME_BROWSER_CONVERSATION
-> SEND_CONTEXT_PACKET
-> RECEIVE_RR_REVIEW
-> EXECUTE_NEXT_WORK_ORDER
-> BUILD_EVIDENCE_PACKET
-> SEND_EVIDENCE_TO_SAME_CONVERSATION
-> RECEIVE_NEXT_REVIEW
-> CONTINUE_OR_STOP
```

Maintain a loop record containing:

```text
WORK_ITEM_ID
CONVERSATION_ID_OR_URL
OPENCLI_PROFILE_IF_EXPLICIT
CREATED_AT
CURRENT_ROUND
LAST_SUCCESSFUL_READ_AT
LAST_SUCCESSFUL_WRITE_AT
CURRENT_STATE
```

Never rely only on the active browser tab. Keep the Conversation ID or URL returned by OpenCLI and echo `WORK_ITEM_ID` in every Packet and expected RR response.

## PRECHECK

Before sending anything, run and record only necessary output from:

```powershell
opencli --version
opencli chatgpt status -f yaml
```

Stop without credential recovery attempts when OpenCLI is missing, Browser Bridge is disconnected, ChatGPT is logged out, a verification/quota/block page appears, or the conversation cannot be read reliably. Never inspect cookies, tokens, API keys, or browser credentials.

The command names and argument shapes below were verified from local OpenCLI `1.8.6` help. Their end-to-end browser behavior remains `UNVERIFIED` until the Transport Smoke Test passes in the current environment:

```powershell
# Candidate first transport: create, send, wait, and return conversationId/conversationUrl.
opencli chatgpt ask "<rr-lead-init + Context Packet + return format>" --new -f yaml

# Candidate continuation: explicitly target the recorded conversation.
opencli chatgpt ask "<Evidence Packet>" --conversation "<conversation-id-or-/c/url>" -f yaml

# Candidate recovery/read: explicitly open the recorded conversation and wait for stability.
opencli chatgpt detail "<conversation-id-or-/c/url>" --wait -f yaml
```

Do not promote these candidates to trusted runtime transport until Experiment A verifies creation, returned identity, explicit continuation, and recovery. `opencli chatgpt new` returns only a status according to local help, so do not use it as the primary identity-capture path. `opencli chatgpt read` reads the current conversation and is insufficient for recovery by itself.

## CREATE_OR_RESUME_BROWSER_CONVERSATION

For a new loop, combine:

1. `assets/rr-lead-init.md`;
2. the current Context Packet;
3. the required review response format.

Use the Transport-Smoke-validated creation command. Capture its Conversation ID and URL instead of guessing or searching by title.

For a resumed loop, use the Transport-Smoke-validated explicit-ID read command, then verify all of the following before sending:

- the opened Conversation ID or URL matches the loop record;
- the latest response contains the same `WORK_ITEM_ID`;
- the latest known `CURRENT_ROUND` and `CURRENT_STATE` are compatible;
- no evidence indicates that a different conversation was opened.

If identity cannot be established, enter `STALLED`; never send to an ambiguous conversation.

## SEND_CONTEXT_PACKET and receive review

Round 0 sends the Context Packet to the verified new or resumed Browser conversation. Parse an actual Browser RR Lead response containing:

```text
WORK_ITEM_ID
REVIEW_DECISION: PASS / PASS_WITH_DEBT / REVISE / ESCALATE
WORK_ITEM_STATE: IN_PROGRESS / ACHIEVED / BLOCKED / NEEDS_DECISION / STALLED / UNSAFE
GOAL_CHECK
FINDINGS
BLOCKERS
DEBT
NEXT_WORK_ORDER
VALIDATION
USER_DECISION_REQUIRED
```

Reject an empty or materially incomplete response. Do not fill missing fields with the IDE-side Loop Driver's judgment.

## EXECUTE_NEXT_WORK_ORDER

Execute `NEXT_WORK_ORDER` only when all conditions hold:

- `WORK_ITEM_STATE` is exactly `IN_PROGRESS`;
- `USER_DECISION_REQUIRED` is false or None;
- the action stays inside user authorization and target-project rules;
- the stated validation is locally executable or can be reported as blocked.

Use appropriate evidence:

- **Code or interactive product:** files, Git diff when Git is used, commands, exit codes, tests, builds, logs, and observable behavior.
- **Teaching or document:** sections, goals, audience, before/after differences, sources, coverage, consistency, and requirement mapping.
- **Research:** sources, type and date, claim mapping, strength, conflicts, uncertainty, freshness, and search boundary.
- **Non-Git:** artifacts, output locations, repeatable checks, acceptance checklist, and observations.

When Git is not used, state that Git evidence is not applicable. Never invent an empty diff, successful command, or verified result.

## BUILD_EVIDENCE_PACKET and continue

Build the Evidence Packet from real results, including failures and acceptance mapping. Send it only to the recorded Conversation ID or URL using the validated continuation path. Parse the next Browser review and repeat until a stop state is reached.

Retry one failed read at most once. If the same instruction fails twice without new evidence, stop repeating it.

## Stop states

- **ACHIEVED:** stop local execution; give the user a plain-language evidence summary and next-stage suggestion.
- **BLOCKED:** stop retrying; identify the missing external condition.
- **STALLED:** stop the loop and generate a Handoff with the conversation identity and last confirmed state.
- **UNSAFE:** stop immediately and do not execute the unsafe action.
- **NEEDS_DECISION:** run the Human-in-the-loop procedure below.

## Human-in-the-loop for NEEDS_DECISION

1. Stop local execution and do not choose for the user.
2. Confirm the actual Browser RR Lead response supplies three plain-language options, their effects, and one recommendation.
3. Tell the user to answer in that Browser conversation.
4. Do not poll automatically. Wait until the user explicitly says they answered.
5. Reopen the recorded Conversation ID or URL through the validated recovery path.
6. Verify `WORK_ITEM_ID`, conversation identity, and the user's explicit decision.
7. Produce a short Decision Receipt containing Work Item, conversation identity, chosen option, decision text, read time, and affected next step.
8. Resume the original loop without executing unchosen options.

## Handle transport and format failures

Treat OpenCLI failure, page changes, Bridge loss, empty output, incomplete RR format, lost Conversation ID, wrong-conversation evidence, and two identical failed attempts as real failures.

- Preserve the original error and last confirmed loop record.
- Never invent a Browser reply or substitute a local review.
- Retry one read once when safe.
- If still unreliable, enter `BLOCKED` for an external connection condition or `STALLED` for lost loop continuity.
- Generate a Handoff and ask the user to repair the browser connection when necessary.

The sixth round is a health checkpoint, not a forced stop. Check goal drift, repetition, missing new evidence, and context reliability.

## Apply safety boundaries

Do not read credentials or unrelated private files; upload, publish, pay, change account permissions, or perform irreversible actions without authorization; or run `git add`, `git stash`, commit, or push by default. The Browser RR Lead advises and reviews; it does not directly control the IDE.
