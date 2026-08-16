# Message Hub Control Plane Migration Specification

## 1. Overview and Migration Objective

This specification establishes the production migration architecture for promoting the **APS Message Hub** from accepted proof-of-concept (PR #8, commit `83a78fccf7556c647d8cf0ae8f59a021e38e4716`) into the authoritative communication control plane candidate of the **Agent Project System (APS)**.

### Architectural Positioning & ADR-0003 Relationship

Per `docs/adr/0003-agent-collaboration-framework.md`, the accepted system layers are:
```text
Agent Project System
→ Agent Collaboration Framework (ADR-0003)
→ Browser Lead / IDE Agent Collaboration Protocol
→ Runtime / Orchestration (Control Plane)
→ Transport / IDE Adapters (Browser Connectors)
```

- **Message Hub:** Candidate implementation of the **Runtime / Orchestration** communication and event control-plane responsibility.
- **OpenCLI:** **Browser / Transport Adapter** operating strictly behind the Message Hub.
- **Minimal Review Bridge (`skills/research-review-lead/`):** Retained as the frozen production and rollback control baseline (PR #3, commit `d7651f95059694047d2a7e280afe761264a54058`) until a future formal cutover decision.
- **Governance Candidate Status:**
  ```ini
  MESSAGE_HUB_CONTROL_PLANE_CANDIDATE=YES
  MESSAGE_HUB_PRODUCTION_MIGRATION_AUTHORIZED=NO
  ```

---

## 2. Production Architecture & Module Boundaries

Production modules will reside under the accepted **Runtime / Orchestration** layer (`runtime/message_hub/`):

```text
runtime/message_hub/
├── __init__.py
├── storage.py              # SQLite Relational Durability & Atomic Claims
├── server.py               # HTTP Gateway & Global/Connector SSE Feed
├── client.py               # Lightweight IDE Client SDK
└── connectors/
    ├── __init__.py
    └── opencli.py          # OpenCLI Browser Adapter & Reconciliation Engine
```

### Module Responsibilities

1. **`runtime/message_hub/storage.py` (Durable Relational Store)**
   - Manages SQLite schema lifecycle, transactional isolation, and ACID durability.
   - Enforces same-thread reply hierarchy and first-class conversation identity.
   - Implements atomic send claims and transactionally verified response creation.

2. **`runtime/message_hub/server.py` (HTTP & SSE Gateway)**
   - Exposes fast durable message submit endpoint returning immediate ACK.
   - Exposes global and connector-filtered SSE feeds with durable cursor (`after_id`) support.
   - Serves secure, HTML-escaped local audit/timeline view.

3. **`runtime/message_hub/client.py` (IDE Client SDK)**
   - Python interface for IDE agents to submit review requests, receive instant durable ACKs, and await `RESPONSE_READY` without blocking execution.

4. **`runtime/message_hub/connectors/opencli.py` (Browser Adapter Connector)**
   - Long-lived background consumer processing `REQUEST_CREATED` events across threads.
   - Validates durable conversation binding from request before external action.
   - Executes atomic SQLite send claim before calling `opencli chatgpt send`.
   - Maps timeouts to `EXTERNAL_SEND_UNKNOWN` with strict zero-resend invariant.
   - Reconciles browser responses via trusted read-only `opencli chatgpt detail` and strictly parses verdicts.

---

## 3. Authoritative Data Model & First-Class Identity

### First-Class Schema (SQLite)

**Explicit Exclusion:** `Task` is **NOT** part of the initial production data model. It is omitted until a concrete multi-agent requirement emerges.

```sql
CREATE TABLE IF NOT EXISTS threads (
    thread_id TEXT PRIMARY KEY,
    title TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    message_id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL,
    conversation_id TEXT NOT NULL,       -- FIRST-CLASS AUTHORITATIVE BINDING
    sender TEXT NOT NULL,
    recipient TEXT NOT NULL,
    message_type TEXT NOT NULL,
    reply_to TEXT,
    artifact_id TEXT,
    content TEXT NOT NULL,
    metadata TEXT NOT NULL DEFAULT '{}', -- Non-authoritative extensible metadata
    status TEXT NOT NULL,
    created_at REAL NOT NULL,
    FOREIGN KEY (thread_id) REFERENCES threads(thread_id)
);

CREATE TABLE IF NOT EXISTS events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id TEXT NOT NULL,
    message_id TEXT,
    event_type TEXT NOT NULL,
    payload TEXT NOT NULL,               -- JSON payload containing event context
    created_at REAL NOT NULL,
    FOREIGN KEY (thread_id) REFERENCES threads(thread_id)
);

CREATE TABLE IF NOT EXISTS send_claims (
    request_id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL,
    claimed_by TEXT NOT NULL,
    claimed_at REAL NOT NULL,
    FOREIGN KEY (thread_id) REFERENCES threads(thread_id)
);

CREATE INDEX IF NOT EXISTS idx_messages_thread ON messages(thread_id);
CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_events_thread ON events(thread_id);
CREATE INDEX IF NOT EXISTS idx_events_id ON events(event_id);
```

---

## 4. Connector Dispatch Topology & Event Resume Contract

### Long-Lived Connector Consumption Model

```text
+--------------------------------------------------------------------------+
|                  Hub Server Global / Connector Event Feed                |
|           GET /api/connectors/<connector_id>/events/stream?after_id=N    |
+--------------------------------------------------------------------------+
                                     │
      1. History Replay (events > N) │ 2. Live Handoff
                                     ▼
+--------------------------------------------------------------------------+
|                        OpenCLI Connector Consumer                        |
|  - Tracks persistent cursor: last_processed_event_id                     |
|  - Filters for event_type == "REQUEST_CREATED"                           |
|  - Reads authoritative `conversation_id` from message row                |
|  - Performs Atomic SQLite Claim: INSERT OR IGNORE INTO send_claims       |
|    * Acquired (1 worker) -> Proceeds to External Send                    |
|    * Conflict / Duplicate -> Emits SKIPPED_ALREADY_ATTEMPTED & drops     |
+--------------------------------------------------------------------------+
```

### Event Resume & Cursor Contract
1. **Reconnection with Cursor:** Clients subscribe with `?after_id=<last_event_id>`.
2. **Replay -> Live Transition:** Server queries durable SQLite `events WHERE event_id > :after_id ORDER BY event_id ASC`, streams existing events, and then transitions seamlessly to live listener queues without dropping events.
3. **Idempotent Delivery Absorption:** If a disconnect occurs during dispatch, replay of `REQUEST_CREATED` is safely absorbed by the SQLite atomic claim (`send_claims` primary key uniqueness) preventing duplicate external execution.

---

## 5. Delivery State Machine & Exactly-Once Response Verification

### Delivery Lifecycle & Invariants

```text
review.request created
         │
         ▼
[REQUEST_CREATED] (Durable in DB & emitted via SSE)
         │
         ▼
Validate durable request.conversation_id == target_browser_conversation_id
         │ (Fail closed if missing/mismatched -> ABORT, zero claim, zero send)
         ▼
Atomic SQLite Claim: INSERT OR IGNORE INTO send_claims (request_id, ...)
         │
         ├── Already claimed -> SKIPPED_ALREADY_ATTEMPTED (no external send)
         │
         └── Acquired (rowcount == 1) -> [CONNECTOR_ACCEPTED]
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
                [EXTERNAL_SEND_COMPLETED] [EXTERNAL_SEND_UNKNOWN] [EXTERNAL_SEND_FAILED]
```

- **Invariant 1:** `EXTERNAL_SEND_UNKNOWN != FAILED` and `EXTERNAL_SEND_UNKNOWN != SAFE_TO_RETRY`.
- **Invariant 2:** Once `EXTERNAL_SEND_ATTEMPTED` or `send_claims` is recorded, **NO AUTOMATIC RESEND IS PERMITTED**.
- **Invariant 3:** `EXTERNAL_SEND_COMPLETED` represents delivery success only; review authority is never minted upon send completion.

### Exactly-Once Concurrent Response Verification (Atomicity Gate)

To prevent race conditions where concurrent reconciliation calls emit duplicate `RESPONSE_READY` continuation signals:
1. **Single SQLite Transaction:**
   ```sql
   BEGIN IMMEDIATE;
   -- 1. Check if response message already exists
   SELECT message_id FROM messages WHERE reply_to = :request_id AND message_type = 'review.response';
   -- 2. If exists -> ROLLBACK and return CACHED_RESPONSE_READY
   -- 3. If absent -> INSERT message AND INSERT event('RESPONSE_READY'); COMMIT;
   ```
2. **Guaranteed Outcome:** Exactly one authoritative `RESPONSE_READY` event is created per `request_id`.

---

## 6. Continuation Contract & Browser Reconciliation Ownership

### Continuation Flow & Trigger Ownership

- **IDE -> Hub:** Fast durable submit ACK.
  - **Invariant:** Durable Hub ACK does not depend on Browser reasoning generation or external send completion.
  - **Evidence:** PoC observed ~20-30ms local submit latency. (No SLA is established).
- **Hub -> Connector:** Event-driven async continuation via Hub SSE feed (`REQUEST_CREATED`).
- **Browser -> Hub:** **Explicit Reconciliation Trigger**.
  - **Limitation:** `REAL_BROWSER_PUSH_INGRESS = NOT_AVAILABLE / NOT_PROVEN`. OpenCLI 1.8.6 has no push notifications or inbound webhooks.
  - **Trigger Owner:** Because the Browser cannot autonomously wake the IDE, reconciliation is explicitly triggered by the **IDE execution outer loop / user** at scheduled checkpoints or review resume actions (`connector.reconcile_browser_response(thread_id, request_id)`).
  - **Push Extensibility:** If a future push-capable Browser adapter is introduced, it will invoke the exact same trusted ingestion function without modifying the core Hub control plane.

---

## 7. Minimal Bridge Coexistence & Honest Rollback Contract

### Coexistence Architecture
- Minimal Bridge (`skills/research-review-lead/`) remains frozen at PR #3 baseline (`d7651f95059694047d2a7e280afe761264a54058`).
- Message Hub operates in parallel during migration verification.

### Honest Rollback Strategy
- **Distinct Stores:** Minimal Bridge disk receipts (`.agent-project-system/receipts/`) and Message Hub SQLite (`hub.db`) are independent stores. **No automatic two-way state synchronization is claimed.**
- **Rollback Protocol:**
  1. Set routing configuration back to Minimal Bridge (`opencli_transport.py`).
  2. Route all NEW review requests to Minimal Bridge.
  3. In-flight Message Hub requests are drained/reconciled in Message Hub before cutback, or re-issued under fresh request IDs on Minimal Bridge.
  4. Message Hub SQLite database is preserved as immutable audit evidence.

---

## 8. Secure Production Observability

### Security & Scope Boundary
- **Safe Output Rendering:** Web timeline endpoints (`GET /threads/<thread_id>`) MUST escape all message content, event payloads, and headers (using standard HTML template escaping or JSON view). Raw `innerHTML` interpolation from untrusted inputs is strictly prohibited.
- **Scope Limit:** Minimal read-only local developer timeline and audit log. No management platform, control triggers, or complex dashboarding.

---

## 9. Phased Implementation Plan (M1 - M5)

### Phase M1: Durable Core & Relational Schema
- **Purpose:** Establish production SQLite schema, connection management, and atomic send/response transactional invariants.
- **Scope:** `runtime/message_hub/storage.py`, first-class `conversation_id`, atomic `try_claim_external_send`, transactional `create_response_and_ready_event`.
- **Non-Goals:** HTTP/SSE networking, OpenCLI connector subprocess calls.
- **Dependencies:** None.
- **Acceptance Criteria:** 100% passing unit tests covering schema creation, deduplication, atomic claim contention (competing threads/processes), and concurrent response creation atomicity.
- **Rollback:** Revert module files.

### Phase M2: HTTP Gateway & Global/Connector SSE Feed
- **Purpose:** Implement HTTP submit API with durable ACK and SSE stream with cursor-based replay.
- **Scope:** `runtime/message_hub/server.py`, `runtime/message_hub/client.py`, `POST /api/threads/<id>/messages`, `GET /api/connectors/<id>/events/stream?after_id=N`.
- **Non-Goals:** OpenCLI external subprocess execution.
- **Dependencies:** M1.
- **Acceptance Criteria:** Replay handoff tests, cursor reconnection tests, client submit ACK latency validation under simulated delay.
- **Rollback:** Revert M2 files.

### Phase M3: OpenCLI Outbound Connector & Atomic Delivery
- **Purpose:** Implement independent background connector worker with durable conversation binding and fail-honest delivery.
- **Scope:** `runtime/message_hub/connectors/opencli.py`, SSE consumer worker, pre-send binding validation, timeout -> `EXTERNAL_SEND_UNKNOWN`, zero-resend enforcement.
- **Non-Goals:** Response reconciliation.
- **Dependencies:** M1, M2.
- **Acceptance Criteria:** Deterministic tests proving pre-send wrong-conversation rejection, runner calls == 1 on contention, timeout conversion to UNKNOWN, restart no-resend.
- **Rollback:** Revert M3 files.

### Phase M4: Trusted Browser Reconciliation & Authority
- **Purpose:** Implement connector-owned trusted browser reading with strict provenance equality and verdict parsing.
- **Scope:** `reconcile_browser_response(...)`, JSON envelope verification, `provenance_conv_id == bound_conv_id` enforcement, `parse_strict_browser_response`.
- **Non-Goals:** Production cutover.
- **Dependencies:** M1, M2, M3.
- **Acceptance Criteria:** Tests proving malformed read fail-closed, mismatched conversation provenance fail-closed, invalid decision rejection, valid verdict -> exactly one `RESPONSE_READY`.
- **Rollback:** Revert M4 files.

### Phase M5: Secure Observability & Coexistence Integration
- **Purpose:** Implement safe HTML-escaped timeline and end-to-end integration validation alongside Minimal Bridge baseline.
- **Scope:** Safe timeline visualization in `server.py`, end-to-end multi-round integration test suite, coexistence configuration switch.
- **Non-Goals:** Deleting Minimal Bridge or automatic PR merge.
- **Dependencies:** M1, M2, M3, M4.
- **Acceptance Criteria:** Full deterministic suite passing, zero HTML injection vulnerabilities in timeline, side-by-side run parity.
- **Rollback:** Revert M5 files.

---

## 10. Final Cutover Gate

Cutover to Message Hub as default control plane requires:
1. Formal completion and acceptance of Phases M1 through M5.
2. 100% green validation across all repository test suites (`check_docs.py`, `check_skill_package.py`, `test_minimal_review_bridge.py`, and Message Hub test suite).
3. Bounded live A/B comparison run demonstrating functional parity against PR #3 baseline.
4. Independent Browser Review `APPROVE` on final cutover PR.
5. Explicit User Decision authorizing production default activation.
