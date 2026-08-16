# Message Hub M1 Execution Packet

WORK_ITEM_ID: APS-MESSAGE-HUB-M1-001

PACKET_STATE: COMPLETED

REQUIRED_PRODUCT_HEAD: d7651f95059694047d2a7e280afe761264a54058

AUTHORITATIVE_ISSUE: https://github.com/carllx/agent-project-system/issues/10

SPECIFICATION_REFERENCE: docs/specs/message-hub-control-plane-migration.md

## Objective and Boundary

This execution packet defines the implementation boundary for APS-MESSAGE-HUB-M1-001 (Message Hub M1 Durable Core).

- **Baseline:** `integration/autonomous-review-loop-main` at `d7651f95059694047d2a7e280afe761264a54058` (PR #3).
- **PoC Reference:** `experiment/message-hub-poc` at `83a78fccf7556c647d8cf0ae8f59a021e38e4716` (PR #8).
- **Scope:** `runtime/message_hub/storage.py` and focused deterministic tests in `tests/test_message_hub_storage.py`.
- **Invariants:** First-class `conversation_id` & `connector_id`, atomic SQLite `send_claims`, durable `connector_cursors`, same-thread reply enforcement, and transactional exactly-once `RESPONSE_READY`.
