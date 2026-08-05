# Context Packet Template

> Reusable temporary message. Do not commit a filled Packet unless project rules require it.

## MESSAGE_IDENTITY

- **WORK_ITEM_ID:** [stable identifier]
- **MESSAGE_ID:** [WORK_ITEM_ID-R0-CONTEXT]
- **ROUND:** 0
- **MESSAGE_TYPE:** CONTEXT_PACKET

## GOAL_CONTRACT

- **SHARED_OBJECTIVE:** [user-confirmed outcome]
- **ACCEPTANCE_CRITERIA:** [numbered observable criteria]
- **SCOPE:** [allowed files, systems, sources, and actions]
- **CONSTRAINTS:** [permissions, privacy, time, environment, or None]
- **EVIDENCE_REQUIRED:** [evidence required per criterion]
- **STOP_CONDITIONS:** ACHIEVED / BLOCKED / NEEDS_DECISION / STALLED / UNSAFE

The Browser RR Lead must judge this contract as written. A newly discovered non-blocking improvement belongs in `DEBT`, not in the acceptance criteria.

## PROJECT_CONTEXT

- **Project type:** [code / interactive product / teaching / document / research / non-Git / other]
- **Authority or guidance entry points:** [paths or None]
- **Relevant materials:** [files, artifacts, sources, or messages]
- **Current state:** [verified progress or unknown]
- **Project location:** [path or not applicable]
- **Git / branch:** [verified values or not applicable]

## VERIFIED_LOCAL_FACTS

[Facts supported by local artifacts, commands, or observations.]

## PROHIBITED_ACTIONS_OR_DATA

[Explicit boundaries, including credentials and unrelated private material.]

## RR_LEAD_QUESTION

[Judgment or next-work-order request; otherwise None.]
