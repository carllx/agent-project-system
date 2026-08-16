---
name: research-review-lead
description: Drive an evidence-based Review loop between an IDE-side execution agent and an independent Browser Review Lead in ChatGPT through the Minimal Browser Review Bridge.
---

# Research Review Lead Skill

## Keep the roles separate

- **IDE Execution Agent:** run in the target project, execute authorized tasks, submit formal Review Requests via the Minimal Bridge, and continue execution via `/goal`.
- **Browser Review Lead:** exist in a real ChatGPT browser conversation; review evidence, judge acceptance criteria, and issue authoritative review decisions.
- **User:** decide goals, costs, accounts, permissions, privacy, irreversible actions, and material scope changes.

The IDE Agent must never impersonate the Browser Review Lead or manufacture a self-review. A local assessment is not a Browser Review Decision.

Use **Full Governance Mode** when the target project has `AGENTS.md` and standard project rules. Do not require Git; when Git is not used, report that Git evidence is not applicable.

## Package Resources

Resolve these bundled assets relative to this `SKILL.md`:

- `assets/rr-lead-init.md`: Browser Review Lead role guidance and JSON response format;
- `assets/context-packet.md`: Goal contract and context;
- `assets/evidence-packet.md`: Verified execution evidence;
- `assets/decision-request.md`: User decision gate;
- `assets/handoff.md`: Continuity handoff;
- `scripts/opencli_transport.py`: Thin CLI facade for the Minimal Bridge;
- `scripts/minimal_bridge.py`: Minimal Browser Review Bridge core.

## Minimal Browser Review Bridge Workflow

Antigravity `/goal` owns the outer task execution and continuation loop. The Minimal Bridge owns exact-identity transport to the Browser Review Lead.

### 1. Establish Conversation (Bootstrap Once)

```powershell
python skills/research-review-lead/scripts/opencli_transport.py review-bootstrap --timeout 30
```

Returns JSON:
```json
{
  "status": "CONVERSATION_ESTABLISHED",
  "conversation_id": "<EXACT_CONVERSATION_UUID>",
  "conversation_url": "..."
}
```

### 2. Fast Submit Review Request

Render canonical envelope, bind `request_id` and `artifact_id`, persist `SEND_ATTEMPTED` receipt, and submit via native `--wait false`:

```powershell
python skills/research-review-lead/scripts/opencli_transport.py review `
  --request-id "REQ-001" `
  --artifact-id "<SHA256_HASH>" `
  --prompt "Verify the implementation against acceptance criteria." `
  --conversation "<EXACT_CONVERSATION_UUID>" `
  --timeout 30
```

Returns immediately:
```json
{
  "status": "RESPONSE_PENDING",
  "request_id": "REQ-001",
  "conversation_id": "<EXACT_CONVERSATION_UUID>",
  "write_attempted": true
}
```

### 3. Read-Only Reconcile (One-Shot Check)

Each reconcile invocation performs exactly one read-only check:

```powershell
python skills/research-review-lead/scripts/opencli_transport.py review `
  --request-id "REQ-001" `
  --artifact-id "<SHA256_HASH>" `
  --conversation "<EXACT_CONVERSATION_UUID>" `
  --reconcile `
  --timeout 30
```

If response is ready:
```json
{
  "status": "RESPONSE_READY",
  "conversation_id": "<EXACT_CONVERSATION_UUID>",
  "response": {
    "request_id": "REQ-001",
    "artifact_id": "<SHA256_HASH>",
    "decision": "APPROVE",
    "feedback": "All criteria met.",
    "next_steps": []
  }
}
```

If still in progress, returns `status: "RESPONSE_PENDING"` and yields control immediately. The current IDE turn must not loop, sleep, manage background tasks, or poll. A later natural `/goal` continuation may perform another explicit reconcile when appropriate.

## Safety Invariants

- **Exact Conversation Binding:** Formal reviews require a known `conversation_id`. If OpenCLI returns a foreign ID, the bridge fails closed and refuses to rebind the receipt.
- **Normalized Identity:** `request_id`, `artifact_id`, and `conversation_id` are normalized at the boundary. Whitespace differences cannot bypass receipt deduplication.
- **At-Most-Once External Write:** `SEND_ATTEMPTED` is recorded atomically before external write. Re-invoking dispatch on the same `request_id` performs read-only reconciliation and never re-sends.
- **Strict Response Parsing:** The bridge requires exactly one JSON response matching `DECISION_CHOICES = {"APPROVE", "REVISE", "BLOCKED"}` and validates `next_steps` as a list of strings.
- **Canonical Receipt Storage:** Production receipt identity is stored in one canonical per-user receipt store and cannot be overridden by the caller.
- **No Busy Polling Loops:** The bridge returns immediately on submit and reconcile without internal sleep or polling loops. Control is handed back to the IDE `/goal` loop.
