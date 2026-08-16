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
├── storage.py              # SQLite Relational Durability, Atomic Claims, Cursor Persistence
├── server.py               # HTTP Gateway & Filtered Connector SSE Feeds
├── client.py               # Lightweight IDE Client SDK
└── connectors/
    ├── __init__.py
    └── opencli.py          # OpenCLI Browser Adapter & Reconciliation Engine
```

### Module Responsibilities

1. **`runtime/message_hub/storage.py` (Durable Relational Store)**
   - Manages SQLite schema lifecycle, transactional isolation, and ACID durability.
   - Enforces first-class `conversation_id` and first-class `connector_id` columns on messages.
   - Implements atomic send claims (`send_claims`), durable connector cursors (`connector_cursors`), and transactionally verified response creation.

2. **`runtime/message_hub/server.py` (HTTP & SSE Gateway)**
   - Exposes fast durable message submit endpoint returning immediate ACK.
   - Exposes connector-targeted SSE feeds (`/api/connectors/<connector_id>/events/stream?after_id=N`) filtered by matching `connector_id`.
   - Serves secure, HTML-escaped local audit/timeline view.

3. **`runtime/message_hub/client.py` (IDE Client SDK)**
   - Python interface for IDE agents to submit review requests, receive instant durable ACKs, and await `RESPONSE_READY` without blocking execution.

4. **`runtime/message_hub/connectors/opencli.py` (Browser Adapter Connector)**
   - Long-lived background consumer processing `REQUEST_CREATED` events matching its `connector_id`.
   - Reads target `conversation_id` directly from authoritative request row.
   - Manages durable cursor advancement in `connector_cursors` strictly after durable handling.
   - Executes atomic SQLite send claim before calling `opencli chatgpt send`.
   - Maps timeouts to `EXTERNAL_SEND_UNKNOWN` with strict zero-resend invariant.
   - Reconciles browser responses via trusted read-only `opencli chatgpt detail` with exact provenance equality verification.

---

## 3. Authoritative Data Model & First-Class Identities

### First-Class Schema (SQLite)

**Explicit Invariant:** `Task` is **NOT** part of the initial production data model. It is omitted until a concrete multi-agent requirement emerges.

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
    conversation_id TEXT NOT NULL,       -- FIRST-CLASS: Exact Browser Conversation UUID
    connector_id TEXT NOT NULL,          -- FIRST-CLASS: Target Transport/Browser Adapter ID
    sender TEXT NOT NULL,
    recipient TEXT NOT NULL,
    message_type TEXT NOT NULL,
    reply_to TEXT,
    artifact_id TEXT,
    content TEXT NOT NULL,
    metadata TEXT NOT NULL DEFAULT '{}', -- Non-authoritative extensible metadata only
    status TEXT NOT NULL,
    created_at REAL NOT NULL,
    FOREIGN KEY (thread_id) REFERENCES threads(thread_id)
);

CREATE TABLE IF NOT EXISTS events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id TEXT NOT NULL,
    message_id TEXT,
    connector_id TEXT,                  -- Target connector ID for stream filtering
    event_type TEXT NOT NULL,
    payload TEXT NOT NULL,              -- JSON payload containing event context
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

CREATE TABLE IF NOT EXISTS connector_cursors (
    connector_id TEXT PRIMARY KEY,
    last_processed_event_id INTEGER NOT NULL,
    updated_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_thread ON messages(thread_id);
CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_events_connector ON events(connector_id, event_id);
CREATE INDEX IF NOT EXISTS idx_events_id ON events(event_id);
```

### Identity Distinction
- `connector_id`: Authoritative identifier for the transport/browser adapter (e.g., `connector:opencli_chatgpt`).
- `conversation_id`: Authoritative UUID for the exact ChatGPT Browser session (e.g., `6a81c528-6004-83ea-af2a-9e5fdbd34c02`).

---

## 4. Connector Dispatch Topology, Cursor Persistence & Resume Contract

### Connector-Specific Event Stream & Targeted Routing

```text
+-------------------------------------------------------------------------------+
|                      Hub Server Connector-Specific Stream                     |
|           GET /api/connectors/<connector_id>/events/stream?after_id=N         |
+-------------------------------------------------------------------------------+
                                        │
         Filter: events.connector_id == <connector_id> AND event_id > N
                                        │
                                        ▼
+-------------------------------------------------------------------------------+
|                       OpenCLI Connector Consumer Worker                       |
|  1. Replay history events > N -> Transition to live SSE queue                 |
|  2. Load request row -> Extract target `conversation_id`                      |
|  3. Atomic Send Claim: INSERT OR IGNORE INTO send_claims (request_id, ...)    |
|     ├── Already claimed -> Log SKIPPED_ALREADY_ATTEMPTED & advance cursor     |
|     └── Acquired -> Execute external write -> Record outcome & advance cursor |
+-------------------------------------------------------------------------------+
```

### Durable Cursor Advancement & Crash Recovery Semantics

1. **Replay Optimization Only:** `connector_cursors.last_processed_event_id` is an event replay/checkpoint optimization; it is **NOT** the at-most-once safety authority.
2. **Safety Authority:** The `send_claims` table and message/event transactional constraints provide the inviolable at-most-once external-send safety guarantee.
3. **Cursor Advancement Order:**
   ```text
   Event received from SSE
            ↓
   Process or reject event to a durable outcome (DB claim acquired / skipped / completed / failed)
            ↓
   Update connector_cursors (SET last_processed_event_id = event_id, updated_at = now())
   ```
4. **Crash Invariant:** If a crash occurs before the cursor is updated, the event will replay upon restart. The replay is safely absorbed by SQLite primary key uniqueness (`send_claims.request_id`), preventing any duplicate external send. **The cursor is NEVER advanced before reaching a durable outcome.**

---

## 5. Delivery State Machine & Exactly-Once Response Verification

### Delivery Lifecycle & Invariants

```text
review.request created (with first-class connector_id & conversation_id)
         │
         ▼
[REQUEST_CREATED] (Durable in DB & emitted to /api/connectors/<connector_id>/events/stream)
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
   SELECT message_id FROM messages WHERE reply_to = :request_id AND message_type = 'review.response';
   -- If exists -> ROLLBACK and return CACHED_RESPONSE_READY
   -- If absent -> INSERT message AND INSERT event('RESPONSE_READY'); COMMIT;
   ```
2. **Guaranteed Outcome:** Exactly one authoritative `RESPONSE_READY` event is created per `request_id`.

---

## 6. Continuation Contract & Browser Reconciliation Ownership

### Continuation Flow & Trigger Ownership

- **IDE -> Hub:** Fast durable submit ACK.
  - **Invariant:** Durable Hub ACK does not depend on Browser reasoning generation or external send completion.
  - **Evidence:** PoC observed ~20-30ms local submit latency. No production SLA is established.
- **Hub -> Connector:** Event-driven async continuation via Hub SSE feed (`REQUEST_CREATED`).
- **Browser -> Hub:** **Explicit Reconciliation Trigger**.
  - **Limitation:** `REAL_BROWSER_PUSH_INGRESS = NOT_AVAILABLE / NOT_PROVEN`. OpenCLI 1.8.6 has no push notifications or inbound webhooks.
  - **Trigger Owner:** Because the Browser cannot autonomously wake the IDE, reconciliation is explicitly triggered by the **IDE execution outer loop / user** at scheduled checkpoints or review resume actions (`connector.reconcile_browser_response(thread_id, request_id)`).
  - **Push Extensibility:** If a future push-capable Browser adapter is introduced, it will invoke the exact same trusted ingestion function without modifying the core Hub control plane.

---

## 7. Minimal Bridge Coexistence & Strict At-Most-Once Rollback Contract

### Coexistence Architecture
- Minimal Bridge (`skills/research-review-lead/`) remains frozen at PR #3 baseline (`d7651f95059694047d2a7e280afe761264a54058`).
- Message Hub operates in parallel during migration verification.
- Canonical Minimal Bridge receipt storage is:
  ```text
  ~/.agent-project-system/browser-review-receipts/
  ```

### Strict At-Most-Once Rollback Protocol
- **Distinct Stores:** Minimal Bridge disk receipts (`~/.agent-project-system/browser-review-receipts/`) and Message Hub SQLite (`hub.db`) are independent stores. **No automatic two-way state synchronization is claimed.**
- **At-Most-Once Safety Rule During Rollback:**
  - A request may be recreated on Minimal Bridge **ONLY IF** it is proven that the Message Hub request **NEVER** acquired an external-send claim (`send_claims`).
  - If a `send_claims` row exists or `EXTERNAL_SEND_ATTEMPTED` was recorded: **NO RESEND VIA MINIMAL BRIDGE IS PERMITTED** (regardless of whether the state was `COMPLETED`, `UNKNOWN`, `FAILED`, or process crashed). Such requests must remain Hub-owned for reconciliation, drained, or explicitly abandoned with audit notes.
- **Rollback Procedure:**
  1. Stop routing NEW review requests to Message Hub.
  2. Classify in-flight Message Hub requests against the `send_claims` boundary.
  3. Unclaimed requests may be re-issued under fresh IDs on Minimal Bridge if required.
  4. Claimed or attempted requests remain Hub-owned for reconciliation or drain.
  5. Route all NEW requests to Minimal Bridge.
  6. Retain Message Hub SQLite database as immutable audit evidence.

---

## 8. Secure Production Observability

### Security & Scope Boundary
- **Safe Output Rendering:** Web timeline endpoints (`GET /threads/<thread_id>`) MUST escape all message content, event payloads, and headers (using standard HTML template escaping or JSON view). Raw `innerHTML` interpolation from untrusted inputs is strictly prohibited.
- **Scope Limit:** Minimal read-only local developer timeline and audit log. No management platform, control triggers, or complex dashboarding.

---

## 9. Phased Implementation Plan with Explicit Browser Gates (M1 - M5)

No phase completion self-authorizes the next phase. Each phase requires explicit independent Browser Review acceptance before the next phase may begin.

### Phase M1: Durable Core & Relational Schema
- **Purpose:** Establish production SQLite schema, connection management, first-class identities, durable cursor table, and atomic send/response transactional invariants.
- **Scope:** `runtime/message_hub/storage.py`, first-class `conversation_id` and `connector_id`, atomic `try_claim_external_send`, transactional `create_response_and_ready_event`, `connector_cursors`.
- **Non-Goals:** HTTP/SSE networking, OpenCLI connector subprocess calls.
- **Dependencies:** None.
- **Acceptance Criteria:** 100% passing unit tests covering schema creation, deduplication, atomic claim contention (competing threads/processes), cursor persistence, and concurrent response creation atomicity.
- **Rollback:** Revert module files.
- **Browser Gate:** **M1 Browser ACCEPT** required before Phase M2 may begin.

### Phase M2: HTTP Gateway & Filtered Connector SSE Feed
- **Purpose:** Implement HTTP submit API with durable ACK and connector-filtered SSE stream with cursor-based replay.
- **Scope:** `runtime/message_hub/server.py`, `runtime/message_hub/client.py`, `POST /api/threads/<id>/messages`, `GET /api/connectors/<connector_id>/events/stream?after_id=N`.
- **Non-Goals:** OpenCLI external subprocess execution.
- **Dependencies:** M1.
- **Acceptance Criteria:** Replay handoff tests, cursor reconnection tests, connector-id filtering tests, client submit ACK latency validation under simulated delay.
- **Rollback:** Revert M2 files.
- **Browser Gate:** **M2 Browser ACCEPT** required before Phase M3 may begin.

### Phase M3: OpenCLI Outbound Connector & Atomic Delivery
- **Purpose:** Implement independent background connector worker with durable conversation binding, durable cursor advancement, and fail-honest delivery.
- **Scope:** `runtime/message_hub/connectors/opencli.py`, SSE consumer worker, pre-send binding validation, post-handling cursor updates, timeout -> `EXTERNAL_SEND_UNKNOWN`, zero-resend invariant.
- **Non-Goals:** Response reconciliation.
- **Dependencies:** M1, M2.
- **Acceptance Criteria:** Deterministic tests proving pre-send wrong-conversation rejection, runner calls == 1 on contention, timeout conversion to UNKNOWN, restart no-resend, cursor crash recovery.
- **Rollback:** Revert M3 files.
- **Browser Gate:** **M3 Browser ACCEPT** required before Phase M4 may begin.

### Phase M4: Trusted Browser Reconciliation & Authority
- **Purpose:** Implement connector-owned trusted browser reading with strict provenance equality and verdict parsing.
- **Scope:** `reconcile_browser_response(...)`, JSON envelope verification, `provenance_conv_id == bound_conv_id` enforcement, `parse_strict_browser_response`.
- **Non-Goals:** Production cutover.
- **Dependencies:** M1, M2, M3.
- **Acceptance Criteria:** Tests proving malformed read fail-closed, mismatched conversation provenance fail-closed, invalid decision rejection, valid verdict -> exactly one `RESPONSE_READY`.
- **Rollback:** Revert M4 files.
- **Browser Gate:** **M4 Browser ACCEPT** required before Phase M5 may begin.

### Phase M5: Secure Observability & Coexistence Integration
- **Purpose:** Implement safe HTML-escaped timeline and end-to-end integration validation alongside Minimal Bridge baseline.
- **Scope:** Safe timeline visualization in `server.py`, end-to-end multi-round integration test suite, coexistence configuration switch.
- **Non-Goals:** Deleting Minimal Bridge or automatic PR merge.
- **Dependencies:** M1, M2, M3, M4.
- **Acceptance Criteria:** Full deterministic suite passing, zero HTML injection vulnerabilities in timeline, side-by-side run parity.
- **Rollback:** Revert M5 files.
- **Browser Gate:** **M5 Browser ACCEPT** required before Final Cutover Evaluation may begin.

---

## 10. Final Production Cutover Gate

Cutover to Message Hub as default control plane requires:
1. Formal completion and independent Browser Review acceptance of Phases M1 through M5.
2. 100% green validation across all repository test suites (`check_docs.py`, `check_skill_package.py`, `test_minimal_review_bridge.py`, and Message Hub test suite).
3. Bounded live A/B comparison run demonstrating functional parity against PR #3 baseline.
4. Independent Browser Review `APPROVE` on final cutover PR.
5. Explicit User Decision authorizing production default activation.
