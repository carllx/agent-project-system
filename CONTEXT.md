# Domain Context and Ubiquitous Language

This document defines the stable ubiquitous language, domain concepts, and architectural boundaries of the **Agent Project System (APS)**.

> **SSOT Notice:** Current execution state, active Work Items, and runtime evidence are tracked exclusively in `docs/current.md`. This document defines domain concepts and architectural terminology only.

## Core Concepts & Terminology

### Agent Project System (APS)
A generalized, IDE-independent and Transport-decoupled framework enabling structured, verifiable, and recoverable multi-agent collaboration loops between Browser-based supervisors and IDE-based execution agents.

### Roles & Responsibilities
- **Browser Review Lead (Supervisor)**: The external reviewer and architecture supervisor operating in a browser chat environment (e.g., ChatGPT). Responsible for technical direction, quality evaluation, work orders, and review decisions. Does not execute local IDE commands directly.
- **IDE Execution Agent**: The execution agent working inside an IDE workspace (e.g., Antigravity). Responsible for implementing contracts, executing local tests, verifying facts, and presenting evidence. Outer continuation is driven by native IDE mechanisms (e.g., Antigravity `/goal`). Cannot self-approve completion.
- **Maintainer / User**: Retains final authority over project goals, scope, account credentials, permissions, financial costs, and irreversible actions.

### Architecture Components
- **Minimal Browser Review Bridge (`minimal_bridge.py`)**: Thin, exact-identity transport bridge between IDE Agent and Browser Review Lead via OpenCLI. Manages deterministic canonical envelope rendering, SHA256 identity binding, atomic receipts, native `--wait false` fast submission, and read-only reconciliation.
- **Execution Packet**: A self-contained, immutable execution contract specified under `docs/references/` and referenced by `docs/references/current-execution-packet.md`.
- **Failure Ledger**: A structured ledger recording proven, inferred, and observed failure modes to prevent repeating invalidated execution paths without modified prerequisites.

### Legacy / Historical ACF Terminology
- **Completion Gate (Historical)**: Previous project-owned completion evaluation machinery, superseded by Antigravity `/goal` outer continuation and the Minimal Browser Review Bridge.
- **Stop Hook / Lifecycle Adapter (Historical)**: Previous experimental IDE stop-interception hook, superseded by native `/goal` loop execution.

## Domain Boundaries & Synonyms to Avoid

- **Do not conflate Transport with Review Authority**: Delivering a message or observing a status does not constitute a valid completion approval.
- **Do not conflate Execution Termination with Completion**: An agent stopping or reaching idle is an IDE lifecycle event, not an architectural task completion.
- **Do not replace `docs/current.md` with `CONTEXT.md`**: `docs/current.md` is the live execution state SSOT; `CONTEXT.md` is the domain glossary and boundary definition.
