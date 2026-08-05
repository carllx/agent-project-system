# Handoff Template

> Use one template for all handoffs. A filled Handoff is a temporary message by default and is not committed unless the user or target-project rules explicitly require it.

Fill the Common Core and only the extension for the role handing off.

## MESSAGE IDENTITY

- **WORK_ITEM_ID:** [stable identifier]
- **MESSAGE_ID:** [WORK_ITEM_ID-Rn-HANDOFF]
- **ROUND:** [number]
- **MESSAGE_TYPE:** HANDOFF

## COMMON CORE

- **Work Item:** [identifier and name; must match WORK_ITEM_ID]
- **Conversation ID:** [if available]
- **Handoff reason:** [why continuity is no longer reliable]
- **Current objective:** [user-confirmed objective]
- **Acceptance criteria:** [remaining criteria]
- **Work Item state:** [IN_PROGRESS / ACHIEVED / BLOCKED / NEEDS_DECISION / STALLED / UNSAFE]

### Confirmed facts

- [facts supported by artifacts, sources, commands, observations, or user decisions]

### Confirmed decisions

- [decisions that must not be reopened without new evidence]

### Blockers

- [acceptance-blocking issues or None]

### Debt

- [non-blocking findings or None]

### Next action

- [one immediately executable and verifiable action]

### Authority entry points to read

- [target-project guidance, state, user request, or other minimum context]

## IDE AGENT EXTENSION

Include only when the IDE or local execution agent is handing off.

- **Project root:** [path or not applicable]
- **Git status:** [verified status when Git is used, otherwise Not applicable]
- **Modified artifacts:** [files, documents, research artifacts, or None]
- **Commands, validation, and errors:** [actual results]
- **Failed paths not to repeat:** [failed approaches lacking new evidence or None]
- **Local environment constraints:** [permissions, tools, data boundaries, or None]

## RR LEAD EXTENSION

Include only when the RR Lead is handing off.

- **Confirmed user goals and preferences:** [facts]
- **External research conclusions and sources:** [findings, citations, and limits]
- **Rejected paths:** [routes excluded and why]
- **Latest review decision:** [PASS / PASS_WITH_DEBT / REVISE / ESCALATE]
- **Current professional judgment:** [rationale]
- **Next Work Order:** [specific instruction and validation]
- **Drift or repetition signals:** [goal drift, repeated advice, missing evidence, or None]
