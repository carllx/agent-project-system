# Research Review Lead Loop Specification

## 1. Purpose and Boundaries

The Research Review Lead Loop defines the evidence-based collaboration protocol between an IDE Execution Agent and an independent Browser Review Lead in ChatGPT via OpenCLI.

```text
Antigravity /goal (Outer Execution & Continuation Loop)
       ↓
Minimal Browser Review Bridge (opencli_transport.py / minimal_bridge.py)
       ↓
OpenCLI (chatgpt ask --wait false / detail)
       ↓
Browser Review Lead (ChatGPT)
```

- **IDE Execution Agent:** Works in the target repository to implement code, run local tests, verify facts, and submit formal Review Requests.
- **Browser Review Lead:** Operates independently in a ChatGPT browser session to review evidence against acceptance criteria and issue authoritative review decisions.
- **User:** Retains final authority over goals, scope, permissions, costs, and irreversible operations.

The IDE Agent must never impersonate the Browser Review Lead or fabricate review decisions.

## 2. Architecture & Responsibilities

- **Antigravity `/goal`:** Owns the outer execution, task planning, and retry continuation loops.
- **Minimal Browser Review Bridge:** Owns exact-identity transport, canonical envelope rendering, SHA256 identity binding, atomic receipts, native `--wait false` fast submission, and read-only reconciliation.
- **OpenCLI:** External CLI adapter executing bounded subprocess calls against ChatGPT.

## 3. Review Lifecycle

### 3.1 Bootstrap Inert Conversation (Once)

The IDE Agent boots an inert review conversation via OpenCLI `--new`:

```bash
python skills/research-review-lead/scripts/opencli_transport.py review-bootstrap --timeout 30
```

Returns:
```json
{
  "status": "CONVERSATION_ESTABLISHED",
  "conversation_id": "<EXACT_CONVERSATION_UUID>",
  "conversation_url": "..."
}
```

### 3.2 Canonical Review Request & Fast Submit

For each review step, the bridge:
1. Normalizes `request_id`, `artifact_id`, and `conversation_id`.
2. Deterministically renders the canonical Review Request envelope:
   ```text
   BROWSER_REVIEW_REQUEST

   REQUEST_ID: <request_id>
   ARTIFACT_ID: <artifact_id>

   REVIEW_TASK:
   <review_prompt>

   REQUIRED_RESPONSE_FORMAT:
   Return exactly one JSON object:
   ```json
   {
     "request_id": "<request_id>",
     "artifact_id": "<artifact_id>",
     "decision": "APPROVE | REVISE | BLOCKED",
     "feedback": "<non-empty string>",
     "next_steps": ["..."]
   }
   ```
   ```
3. Computes the SHA256 `request_hash` of the rendered canonical text.
4. Persists an atomic receipt in `PREPARED` state, updated to `SEND_ATTEMPTED` immediately before the external write.
5. Invokes OpenCLI with native `--wait false`:
   ```bash
   opencli chatgpt ask --conversation <conversation_id> --wait false -f json "<CANONICAL_MESSAGE>"
   ```
6. Returns `status: "RESPONSE_PENDING"` immediately without blocking on assistant reasoning generation.

### 3.3 One-Shot Read-Only Reconcile

When checking review progress, the IDE Agent executes a one-shot read-only reconciliation:

```bash
python skills/research-review-lead/scripts/opencli_transport.py review \
  --request-id "<request_id>" \
  --artifact-id "<artifact_id>" \
  --conversation "<conversation_id>" \
  --reconcile \
  --timeout 30
```

1. Validates `receipt.request_id == query.request_id`, `receipt.artifact_id == query.artifact_id`, and `receipt.conversation_id == query.conversation_id`.
2. Calls read-only `opencli chatgpt detail <conversation_id> -f json`.
3. Parses assistant messages with strict single-JSON validation.
4. If a matching response is parsed, marks receipt `RESPONSE_RECEIVED` and returns `status: "RESPONSE_READY"`.
5. If still generating, returns `status: "RESPONSE_PENDING"` and immediately yields control.

### 3.4 Outer Continuation

- If `APPROVE`: The IDE Agent proceeds to the next milestone or completes the task.
- If `REVISE`: The IDE Agent executes the requested revisions, generates new artifact hash and request ID, and submits a new review step.
- If `BLOCKED`: The IDE Agent halts execution and requests user intervention.

## 4. Safety Invariants

- **Browser Review Authority:** The IDE Agent cannot self-approve completion.
- **Exact Conversation Non-Drift:** Formal dispatch requires a known `conversation_id`. If OpenCLI returns a foreign ID, the bridge fails closed, preserves the original target, and refuses to rebind.
- **Normalized Identity & At-Most-Once Write:** Request IDs are normalized at boundaries. Once a request reaches `SEND_ATTEMPTED`, subsequent dispatch calls automatically fall back to read-only reconciliation and never re-send.
- **Strict Response Grammar:** The bridge accepts exactly one JSON object matching `DECISION_CHOICES = {"APPROVE", "REVISE", "BLOCKED"}` with non-empty `feedback` and `list[str]` `next_steps`. Responses containing multiple JSON blocks or extraneous JSON outside the fence are rejected.
- **Exact Returned Identity:** Browser-returned `request_id` and `artifact_id` must match expected values with zero leading or trailing whitespace.
- **Canonical Receipt Storage:** Production receipt identity is stored in one canonical per-user receipt store (`~/.agent-project-system/browser-review-receipts`) and cannot be overridden by the caller.
- **Zero Polling Loops:** Neither dispatch nor reconcile contain internal sleep or polling loops.
- **Bounded Command Execution:** All OpenCLI subprocess invocations enforce a strict 30-second bounded timeout.
