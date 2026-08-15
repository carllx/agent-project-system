# Domain Context and Ubiquitous Language

This document defines the stable ubiquitous language, domain concepts, and architectural boundaries of the **Agent Project System (APS)**.

> **SSOT Notice:** Current execution state, active Work Items, and runtime evidence are tracked exclusively in `docs/current.md`. This document defines domain concepts and architectural terminology only.

## Core Concepts & Terminology

### Agent Project System (APS)
A generalized, IDE-independent and Transport-decoupled framework enabling structured, verifiable, and recoverable multi-agent collaboration loops between Browser-based supervisors and IDE-based execution agents.

### Agent Collaboration Framework (ACF)
The overarching architectural framework enabling structured collaboration loops between execution agents and supervisors. Key domain concepts include:
- **Review Request**: Structured artifact submitted by the execution agent containing task identity, agreed acceptance criteria, and verified execution evidence.
- **Review Decision**: Structured supervisor evaluation assessing submitted evidence against acceptance criteria and issuing explicit work orders or decisions.

See `docs/adr/0003-agent-collaboration-framework.md` and applicable registered specs for normative protocol details.

### Roles & Responsibilities
- **Browser Lead (Supervisor)**: The external reviewer and architecture supervisor operating in a browser chat environment (e.g., ChatGPT). Responsible for technical direction, quality evaluation, work orders, and review decisions. Does not execute local IDE commands directly.
- **Product Agent (IDE Execution Agent)**: The execution agent working inside an IDE workspace (e.g., Antigravity, Codex). Responsible for implementing contracts, executing local tests, verifying facts, and presenting evidence. Cannot self-approve completion.
- **Lab Agent (`rr-lead-skill-lab`)**: An isolated environment and agent role strictly dedicated to hypothesis testing, probe validation, and exploratory evidence collection. Never mutates Product source code directly.
- **Maintainer / User**: Retains final authority over project goals, scope, account credentials, permissions, financial costs, and irreversible actions.

### Architecture Components
- **Completion Gate**: An IDE-independent verification policy ensuring a Work Item only transitions to `COMPLETED` upon a verified, un-stale, matching supervisor `APPROVE` where all agreed criteria are `MET`. Execution termination is decoupled from Completion Authority.
- **Lifecycle Adapter / Stop Hook**: IDE-specific bridge (such as Antigravity Stop Hook) translating IDE lifecycle events (stop/idle/turn completion) into ACF completion gate evaluations and bounded continuations.
- **Transport Adapter**: Communication layer (e.g. OpenCLI Transport) handling message delivery, conversation identity tracking, and receipt verification between IDE and Browser Lead without assuming completion authority.
- **Execution Packet**: A self-contained, immutable execution contract specified under `docs/references/` and referenced by `docs/references/current-execution-packet.md`.
- **Failure Ledger**: A structured ledger recording proven, inferred, and observed failure modes to prevent repeating invalidated execution paths without modified prerequisites.

## Domain Boundaries & Synonyms to Avoid

- **Do not conflate Transport with Completion Authority**: Delivering a message or observing a status does not constitute a valid completion approval.
- **Do not conflate Execution Termination with Completion**: An agent stopping or reaching idle is an IDE lifecycle event, not an architectural task completion.
- **Do not conflate Lab Probes with Product Source**: Probe results in lab repositories are external evidence, not production code modifications.
- **Do not replace `docs/current.md` with `CONTEXT.md`**: `docs/current.md` is the live execution state SSOT; `CONTEXT.md` is the domain glossary and boundary definition.
