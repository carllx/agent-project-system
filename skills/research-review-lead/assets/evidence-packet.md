# Evidence Packet Template

> Reusable template. A filled Packet is a temporary message by default, not a project file.

Return successful and failed evidence honestly. Use the common core for every project, then include only the applicable project-type fields. Do not fabricate empty Git evidence when Git is not used.

## OBJECTIVE

[The objective actually executed or investigated.]

## SCOPE

- **Allowed scope used:** [files, materials, systems, or sources]
- **Actions performed:** [concise list]
- **Actions deliberately not performed:** [boundaries respected]

## ARTIFACT_CHANGES

[Changed files, sections, research conclusions, or produced artifacts and their locations. Write None when nothing changed.]

## VERIFICATION

[Repeatable checks and actual results, including failures. Commands and exit codes are required only when commands are relevant.]

## SOURCES

[Local artifacts, cited sources, user decisions, or other evidence supporting the result.]

## UNCERTAINTY

[Unverified claims, missing evidence, conflicts, freshness limits, or None.]

## ACCEPTANCE_MAPPING

| Acceptance criterion | Evidence | Result |
| --- | --- | --- |
| [criterion] | [specific evidence] | [pass / fail / unverified] |

## BLOCKERS

[Only issues preventing the current acceptance criteria; otherwise None.]

## DEBT

[Non-blocking findings or future improvements; otherwise None.]

## Conditional evidence: code or interactive product

- **Changed files:** [paths]
- **Git evidence:** [diff/stat when Git is used, otherwise Not applicable]
- **Commands and exit codes:** [when applicable]
- **Tests / builds / logs:** [actual results]
- **Observable behavior:** [interaction or runtime evidence]

## Conditional evidence: teaching or document

- **Changed sections:** [chapters or sections]
- **Goals and audience:** [teaching goals and intended audience]
- **Before/after difference:** [material changes]
- **Sources and coverage:** [citations, coverage, consistency]
- **User-requirement mapping:** [how requirements were checked]

## Conditional evidence: research

- **Source, type, and date:** [per source]
- **Claim mapping and evidence strength:** [supported conclusions]
- **Conflicting information:** [conflicts or None]
- **Freshness and search boundary:** [limits]

## Conditional evidence: non-Git

- **Changed files or artifacts:** [paths or descriptions]
- **Actual output location:** [location]
- **Repeatable review steps:** [steps]
- **Acceptance checklist and observations:** [actual results]
