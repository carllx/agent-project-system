# Evidence Packet Template

> Reusable temporary message. Report successes and failures honestly; include only applicable conditional evidence.

## MESSAGE_IDENTITY

- **WORK_ITEM_ID:** [stable identifier]
- **MESSAGE_ID:** [WORK_ITEM_ID-R1-EVIDENCE]
- **ROUND:** [number]
- **MESSAGE_TYPE:** EVIDENCE_PACKET

## GOAL_CONTRACT_REFERENCE

- **SHARED_OBJECTIVE:** [same objective as Context Packet]
- **ACCEPTANCE_CRITERIA:** [same numbered criteria; do not silently add conditions]

## EXECUTION

- **NEXT_WORK_ORDER executed:** [quoted or summarized instruction]
- **Allowed scope used:** [files, materials, systems, or sources]
- **Actions performed:** [concise list]
- **Actions deliberately not performed:** [boundaries respected]

## ARTIFACT_CHANGES

[Changed files, sections, conclusions, or output locations; use None when unchanged.]

## VERIFICATION

[Repeatable checks and actual results, including failures. Commands and exit codes are required only when relevant.]

## SOURCES

[Local artifacts, cited sources, user decisions, or other supporting evidence.]

## UNCERTAINTY

[Unverified claims, conflicts, freshness limits, or None.]

## ACCEPTANCE_MAPPING

| Criterion | Evidence | Status |
| --- | --- | --- |
| [criterion] | [specific evidence] | MET / NOT_MET / UNVERIFIED |

## BLOCKERS

[Only issues preventing current acceptance criteria; otherwise None.]

## DEBT

[Non-blocking findings or future improvements; otherwise None.]

## CONDITIONAL_EVIDENCE

- **Code / product:** [changed paths, Git diff when Git is used, commands, tests, logs, observable behavior]
- **Teaching / document:** [changed sections, goals, audience, before/after, sources, coverage, requirement mapping]
- **Research:** [source/type/date, claim mapping, strength, conflicts, freshness and search boundary]
- **Non-Git:** [artifact paths, repeatable checks, acceptance observations; Git evidence is not applicable]
