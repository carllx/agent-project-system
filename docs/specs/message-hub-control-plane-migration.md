# Message Hub Control Plane Migration Specification

## 1. Overview and Migration Objective

This specification establishes the production migration architecture for promoting the **APS Message Hub** from accepted proof-of-concept (PR #8, commit `83a78fccf7556c647d8cf0ae8f59a021e38e4716`) into the authoritative communication control plane of the **Agent Project System (APS)**.

### Architectural Positioning

Per `docs/adr/0003-agent-collaboration-framework.md`:
- **APS Control Plane (Message Hub):** Owns durable thread/message/event storage, fast submit ACKs, delivery claims, event distribution (SSE), and trusted response reconciliation.
- **Browser Adapter (OpenCLI):** Operates strictly as an external transport connector behind the Message Hub.
- **Minimal Review Bridge (`skills/research-review-lead/`):** Retained as the frozen rollback and control baseline (PR #3, commit `d7651f95059694047d2a7e280afe761264a54058`) until formal cutover gating.

```text
+-------------------------------------------------------------------------+
|                              IDE Agent                                  |
|   (Fast submit / Submits review.request / Receives SSE RESPONSE_READY)  |
+-------------------------------------------------------------------------+
                                    │
                         Durable Hub ACK (20-30ms)
                                    │
                                    ▼
+-------------------------------------------------------------------------+
|                       APS Message Hub (Control Plane)                   |
|  - SQLite relational store (Threads, Messages, Events, Send Claims)     |
|  - Atomic External-Send Claim Gate (1 Worker only)                      |
|  - SSE Event Publisher (/api/threads/<id>/events/stream)                |
|  - Web Timeline Observability (/threads/<id>)                           |
+-------------------------------------------------------------------------+
                                    │
                   Event push: REQUEST_CREATED (SSE)
                                    │
                                    ▼
+-------------------------------------------------------------------------+
|                  OpenCLI Browser Connector (Adapter)                    |
|  - Validates durable request -> conversation binding                    |
|  - Acquires SQLite send claim atomically                                |
|  - Records EXTERNAL_SEND_ATTEMPTED before external write                |
|  - Invokes `opencli chatgpt send` (submit-only)                         |
|  - Timeout -> EXTERNAL_SEND_UNKNOWN (zero auto-resend)                  |
|  - Reconciles via `opencli chatgpt detail` with exact provenance checks |
+-------------------------------------------------------------------------+
                                    │
                               Subprocess
                                    │
                                    ▼
+-------------------------------------------------------------------------+
|                      Browser Review Lead (ChatGPT)                      |
|  - Evaluates review evidence in browser                                 |
|  - Produces authoritative verdict JSON (APPROVE | REVISE | BLOCKED)     |
+-------------------------------------------------------------------------+
```

---

## 2. Production Architecture & Module Boundaries

Production modules will reside in a dedicated core package rather than a flat prototype directory:

1. **`core/message_hub/storage.py` (Durable Relational Store)**
   - Encapsulates SQLite schema, connection lifecycle, and transactional boundaries.
   - Tables:
     - `threads`: `thread_id` (PK), `title`, `created_at`, `updated_at`.
     - `messages`: `message_id` (PK), `thread_id` (FK), `sender`, `recipient`, `message_type`, `reply_to`, `artifact_id`, `content`, `metadata` (JSON text containing `conversation_id`), `status`, `created_at`.
     - `events`: `event_id` (PK auto), `thread_id` (FK), `message_id`, `event_type`, `payload` (JSON text), `created_at`.
     - `send_claims`: `request_id` (PK), `thread_id` (FK), `claimed_by`, `claimed_at`.
   - Invariants: Same-thread reply constraint, exact deduplication on identical message payload, conflict rejection on conflicting re-submission, atomic `try_claim_external_send`.

2. **`core/message_hub/server.py` (HTTP & SSE Gateway)**
   - HTTP endpoints:
     - `POST /api/threads/<thread_id>/messages`: Submit message, return durable `{status: "ACK", is_new: bool, message: ...}` immediately.
     - `GET /api/threads/<thread_id>/events/stream`: SSE endpoint with zero-loss replay handoff to live listener queue.
     - `GET /threads/<thread_id>`: Web timeline HTML visualization.

3. **`core/message_hub/client.py` (IDE Client SDK)**
   - Lightweight client providing `submit_review_request(...)`, `listen_events(...)`, and `wait_for_response(...)`.

4. **`core/message_hub/connectors/opencli.py` (Browser Adapter Connector)**
   - Independent background event worker listening to SSE for `REQUEST_CREATED`.
   - Enforces pre-send durable conversation binding.
   - Enforces atomic claim acquisition.
   - Enforces failure-honest transitions and zero auto-resend.
   - Provides connector-owned `reconcile_browser_response(...)` with exact provenance equality verification.

---

## 3. Delivery & Review Authority State Machine

### External Send Delivery Lifecycle

```text
review.request created
         │
         ▼
[REQUEST_CREATED] (Durable in DB & emitted via SSE)
         │
         ▼
Validate durable request.metadata.conversation_id == worker.conversation_id
         │ (Fail closed if missing/mismatched -> ABORT, zero claim, zero send)
         ▼
Atomic SQLite Claim: INSERT INTO send_claims (request_id, ...)
         │
         ├── Already claimed -> SKIPPED_ALREADY_ATTEMPTED (no external send)
         │
         └── Acquired -> [CONNECTOR_ACCEPTED]
                                │
                                ▼
               [EXTERNAL_SEND_ATTEMPTED] (Persisted BEFORE subprocess)
                                │
                                ▼
               Invoke `opencli chatgpt send`
                                │
          ┌─────────────────────┼─────────────────────┐
          ▼                     ▼                     ▼
     Exit Code 0           Exit Code 124          Non-zero Exit
          │                     │                     │
          ▼                     ▼                     ▼
[EXTERNAL_SEND_COMPLETED]  [EXTERNAL_SEND_UNKNOWN]  [EXTERNAL_SEND_FAILED]
```

### Critical Invariants
1. `EXTERNAL_SEND_UNKNOWN != FAILED` and `EXTERNAL_SEND_UNKNOWN != SAFE_TO_RETRY`.
2. Once `EXTERNAL_SEND_ATTEMPTED` or `send_claims` is recorded, **NO AUTOMATIC RESEND IS PERMITTED**.
3. Delivery completion (`EXTERNAL_SEND_COMPLETED`) confirms dispatch transport only; it **does NOT** grant review approval.

### Review Authority & Provenance Lifecycle
1. Reconciliation is initiated via `connector.reconcile_browser_response(thread_id, request_id)`.
2. Connector calls `opencli chatgpt detail <bound_conversation_id> -f json`.
3. If JSON envelope is malformed or unparseable: **FAILS CLOSED** (zero `review.response`, zero `RESPONSE_READY`).
4. If output exposes an explicit `conversationId` that differs from `bound_conversation_id`: **FAILS CLOSED** with `Conversation provenance mismatch`.
5. Verdict parsed strictly via `parse_strict_browser_response` for `request_id`, `artifact_id`, and `decision` in `{"APPROVE", "REVISE", "BLOCKED"}`.
6. Emits authoritative `RESPONSE_READY` only when all criteria pass.
7. Subsequent calls return `CACHED_RESPONSE_READY` without duplicating events.

---

## 4. Continuation Contract & Ingress Classification

- **IDE -> Hub:** Fast durable submit ACK (20-30ms wallclock). Unblocks IDE main loop immediately.
- **Hub -> Browser Connector:** Event-driven push via Hub SSE stream (`REQUEST_CREATED`). No database polling loops.
- **Browser -> Hub:** Explicit read-only reconciliation (`reconcile_browser_response`).
- **Ingress Classification:**
  ```text
  REAL_BROWSER_PUSH_INGRESS = NOT_AVAILABLE / NOT_PROVEN
  ```
  OpenCLI 1.8.6 exposes no inbound webhook or event stream for ChatGPT generation completion. APS does not introduce busy polling loops to simulate push ingress. Future push-capable adapters may be added without modifying the core control plane.

---

## 5. Minimal Bridge Coexistence & Rollback Strategy

1. **Coexistence Phase:** Minimal Bridge (`skills/research-review-lead/`) remains frozen at PR #3 baseline (`d7651f95059694047d2a7e280afe761264a54058`).
2. **Rollback Boundary:** If Message Hub encounters unrecoverable regressions, system config points back to `opencli_transport.py` CLI facade without data loss or schema conflict.
3. **Cutover Gate:** Minimal Bridge retirement requires:
   - Full implementation of production Message Hub package with 100% passing regression suites.
   - Clean multi-round live A/B parity proof.
   - Explicit Browser Review `APPROVE` and User Authorization.

---

## 6. Selective-Promotion Strategy (PoC -> Production)

- **Port Cleanly:**
  - ACID schema and atomic SQLite claim logic from `prototype/message-hub/storage.py`.
  - HTTP/SSE server and zero-loss history replay handoff from `prototype/message-hub/server.py`.
  - Connector lifecycle, durable binding, and strict provenance parsing from `prototype/message-hub/opencli_connector.py`.
  - IDE client wrapper from `prototype/message-hub/client_ide.py`.
  - Deterministic test scenarios from `prototype/message-hub/test_message_hub.py`.
- **Leave Behind in Prototype / PR #8:**
  - Flat prototype directory structure.
  - Scratch evaluation scripts and ad-hoc test runners.
  - Intermediate experiment logs.

---

## 7. Phased Implementation Plan

- **Phase M1 (Durable Core & Schema):** Formal package layout, SQLite tables, atomic claims, strict message/event invariants.
- **Phase M2 (Server & Event Distribution):** HTTP API, SSE replay/live stream handoff, lightweight IDE client.
- **Phase M3 (OpenCLI Browser Connector):** Background SSE worker, durable conversation binding, atomic send execution, timeout->UNKNOWN.
- **Phase M4 (Trusted Browser Reconciliation):** Read-only reconciliation, strict verdict parsing, provenance validation, duplicate caching.
- **Phase M5 (Observability & Integration Cutover):** Timeline visualization, recovery verification, live comparative validation against PR #3 baseline.
