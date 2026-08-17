"""Focused deterministic unit and concurrency test suite for Message Hub M1 Storage."""

from __future__ import annotations

import concurrent.futures
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path

from runtime.message_hub.storage import (
    ConflictError,
    CursorError,
    Storage,
    ThreadIntegrityError,
)


class TestMessageHubM1Storage(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_hub.db"
        self.storage = Storage(self.db_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    # -------------------------------------------------------------------------
    # 1. Schema Bootstrap & Reopen Persistence
    # -------------------------------------------------------------------------
    def test_schema_bootstrap_and_reopen_persistence(self) -> None:
        thread = self.storage.create_thread("t-001", "Main Thread")
        self.assertEqual(thread.thread_id, "t-001")
        self.assertEqual(thread.title, "Main Thread")

        msg, is_new = self.storage.create_message(
            thread_id="t-001",
            message_id="m-001",
            conversation_id="conv-uuid-1",
            connector_id="connector:opencli_chatgpt",
            sender="agent:ide",
            recipient="agent:browser_lead",
            message_type="review.request",
            content="Please review this artifact",
            artifact_id="art-101",
        )
        self.assertTrue(is_new)
        self.assertEqual(msg.message_id, "m-001")

        # Reopen database with fresh Storage instance
        storage2 = Storage(self.db_path)
        fetched_thread = storage2.get_thread("t-001")
        self.assertIsNotNone(fetched_thread)
        self.assertEqual(fetched_thread.title, "Main Thread")

        fetched_msg = storage2.get_message("m-001")
        self.assertIsNotNone(fetched_msg)
        self.assertEqual(fetched_msg.conversation_id, "conv-uuid-1")
        self.assertEqual(fetched_msg.connector_id, "connector:opencli_chatgpt")
        self.assertEqual(fetched_msg.artifact_id, "art-101")

    # -------------------------------------------------------------------------
    # 2. Reserved Message Type review.response Enforcement
    # -------------------------------------------------------------------------
    def test_generic_create_message_rejects_reserved_review_response(self) -> None:
        self.storage.create_thread("t-reserved")
        with self.assertRaises(ConflictError) as ctx:
            self.storage.create_message(
                thread_id="t-reserved",
                message_id="resp-unauthorized",
                conversation_id="conv-1",
                connector_id="conn-1",
                sender="browser",
                recipient="ide",
                message_type="review.response",
                content="Illegal bypass",
            )
        self.assertIn("Reserved message_type", str(ctx.exception))
        # Ensure nothing was written
        self.assertIsNone(self.storage.get_message("resp-unauthorized"))
        events = self.storage.get_events(thread_id="t-reserved")
        self.assertEqual(len(events), 0)

    # -------------------------------------------------------------------------
    # 3. Identical Message Deduplication and Conflicting Same-ID Rejection
    # -------------------------------------------------------------------------
    def test_identical_message_dedup_and_conflicting_payload_rejection(self) -> None:
        self.storage.create_thread("t-001")
        msg1, is_new1 = self.storage.create_message(
            thread_id="t-001",
            message_id="req-1",
            conversation_id="conv-1",
            connector_id="connector:opencli",
            sender="ide",
            recipient="browser",
            message_type="review.request",
            content="Check file A",
            artifact_id="art-1",
            metadata={"priority": "high"},
        )
        self.assertTrue(is_new1)

        # Exact same submission -> returns existing, is_new=False
        msg2, is_new2 = self.storage.create_message(
            thread_id="t-001",
            message_id="req-1",
            conversation_id="conv-1",
            connector_id="connector:opencli",
            sender="ide",
            recipient="browser",
            message_type="review.request",
            content="Check file A",
            artifact_id="art-1",
            metadata={"priority": "high"},
        )
        self.assertFalse(is_new2)
        self.assertEqual(msg1.message_id, msg2.message_id)

        # Conflicting content with same message_id -> ConflictError
        with self.assertRaises(ConflictError):
            self.storage.create_message(
                thread_id="t-001",
                message_id="req-1",
                conversation_id="conv-1",
                connector_id="connector:opencli",
                sender="ide",
                recipient="browser",
                message_type="review.request",
                content="Check file B - CONFLICTING",
                artifact_id="art-1",
            )

        # Conflicting conversation_id with same message_id -> ConflictError
        with self.assertRaises(ConflictError):
            self.storage.create_message(
                thread_id="t-001",
                message_id="req-1",
                conversation_id="conv-DIFFERENT-UUID",
                connector_id="connector:opencli",
                sender="ide",
                recipient="browser",
                message_type="review.request",
                content="Check file A",
                artifact_id="art-1",
            )

    # -------------------------------------------------------------------------
    # 4. Same-Thread Reply Hierarchy and Cross-Thread Rejection
    # -------------------------------------------------------------------------
    def test_same_thread_reply_and_cross_thread_rejection(self) -> None:
        self.storage.create_thread("thread-A")
        self.storage.create_thread("thread-B")

        self.storage.create_message(
            thread_id="thread-A",
            message_id="req-A",
            conversation_id="conv-A",
            connector_id="conn-1",
            sender="ide",
            recipient="browser",
            message_type="review.request",
            content="Review A",
        )

        # Valid non-authoritative reply in thread-A
        reply_a, is_new = self.storage.create_message(
            thread_id="thread-A",
            message_id="msg-reply-A",
            conversation_id="conv-A",
            connector_id="conn-1",
            sender="browser",
            recipient="ide",
            message_type="note.reply",
            reply_to="req-A",
            content="Understood note",
        )
        self.assertTrue(is_new)
        self.assertEqual(reply_a.reply_to, "req-A")

        # Invalid cross-thread reply: message in thread-B replying to req-A in thread-A
        with self.assertRaises(ThreadIntegrityError):
            self.storage.create_message(
                thread_id="thread-B",
                message_id="msg-reply-B",
                conversation_id="conv-B",
                connector_id="conn-1",
                sender="browser",
                recipient="ide",
                message_type="note.reply",
                reply_to="req-A",
                content="Cross-thread attack",
            )

        # Invalid reply to non-existent message
        with self.assertRaises(ThreadIntegrityError):
            self.storage.create_message(
                thread_id="thread-A",
                message_id="msg-ghost",
                conversation_id="conv-A",
                connector_id="conn-1",
                sender="browser",
                recipient="ide",
                message_type="note.reply",
                reply_to="non-existent-parent",
                content="Ghost reply",
            )

    # -------------------------------------------------------------------------
    # 5. First-Class Identities (connector_id & conversation_id)
    # -------------------------------------------------------------------------
    def test_first_class_identities_persisted_and_validated(self) -> None:
        self.storage.create_thread("t-1")
        msg, _ = self.storage.create_message(
            thread_id="t-1",
            message_id="msg-typed",
            conversation_id="chatgpt-conv-uuid-999",
            connector_id="connector:opencli_chatgpt",
            sender="ide",
            recipient="browser",
            message_type="review.request",
            content="Task content",
            metadata={"arbitrary_key": "arbitrary_val"},
        )
        self.assertEqual(msg.conversation_id, "chatgpt-conv-uuid-999")
        self.assertEqual(msg.connector_id, "connector:opencli_chatgpt")
        self.assertEqual(msg.metadata.get("arbitrary_key"), "arbitrary_val")

        with self.assertRaises(ValueError):
            self.storage.create_message(
                thread_id="t-1",
                message_id="m-bad-conv",
                conversation_id="   ",
                connector_id="connector:opencli",
                sender="ide",
                recipient="browser",
                message_type="review.request",
                content="c",
            )
        with self.assertRaises(ValueError):
            self.storage.create_message(
                thread_id="t-1",
                message_id="m-bad-conn",
                conversation_id="conv-1",
                connector_id="",
                sender="ide",
                recipient="browser",
                message_type="review.request",
                content="c",
            )

    # -------------------------------------------------------------------------
    # 6. Atomic Send Claim Bound to Real Request & Contention
    # -------------------------------------------------------------------------
    def test_send_claim_requires_real_review_request(self) -> None:
        self.storage.create_thread("t-claim-bind")
        self.storage.create_thread("t-other")

        # 1. Missing request fails closed
        with self.assertRaises(ThreadIntegrityError):
            self.storage.try_claim_external_send("non-existent-req", "t-claim-bind", "worker-1")

        # 2. Non-review.request message fails closed
        self.storage.create_message(
            thread_id="t-claim-bind",
            message_id="msg-info",
            conversation_id="conv-1",
            connector_id="conn-1",
            sender="ide",
            recipient="browser",
            message_type="chat.note",
            content="Just a note",
        )
        with self.assertRaises(ConflictError):
            self.storage.try_claim_external_send("msg-info", "t-claim-bind", "worker-1")

        # 3. Wrong thread fails closed
        self.storage.create_message(
            thread_id="t-claim-bind",
            message_id="req-valid",
            conversation_id="conv-1",
            connector_id="conn-1",
            sender="ide",
            recipient="browser",
            message_type="review.request",
            content="Review this",
        )
        with self.assertRaises(ThreadIntegrityError):
            self.storage.try_claim_external_send("req-valid", "t-other", "worker-1")

    def test_atomic_send_claim_contention_and_restart_persistence(self) -> None:
        self.storage.create_thread("t-claim")
        req_id = "req-contend-001"
        self.storage.create_message(
            thread_id="t-claim",
            message_id=req_id,
            conversation_id="conv-claim",
            connector_id="conn-claim",
            sender="ide",
            recipient="browser",
            message_type="review.request",
            content="Review",
        )

        barrier = threading.Barrier(10)

        def try_claim(worker_name: str) -> bool:
            barrier.wait()
            st = Storage(self.db_path)
            return st.try_claim_external_send(req_id, "t-claim", worker_name)

        workers = [f"worker-{i}" for i in range(10)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(try_claim, workers))

        # Exactly one worker won the claim
        self.assertEqual(results.count(True), 1)
        self.assertEqual(results.count(False), 9)

        # Inspect winner
        claim = self.storage.get_send_claim(req_id)
        self.assertIsNotNone(claim)
        self.assertIn(claim.claimed_by, workers)

        # Claim persists across DB reopen
        storage_reopen = Storage(self.db_path)
        reopened_claim = storage_reopen.get_send_claim(req_id)
        self.assertIsNotNone(reopened_claim)
        self.assertEqual(reopened_claim.claimed_by, claim.claimed_by)

        # Attempting to re-claim returns False (no permission for second external send)
        self.assertFalse(storage_reopen.try_claim_external_send(req_id, "t-claim", "worker-replay"))

    # -------------------------------------------------------------------------
    # 7. Connector Cursor Validation & Concurrent Monotonicity
    # -------------------------------------------------------------------------
    def test_connector_cursor_validation_and_monotonicity(self) -> None:
        self.storage.create_thread("t-cur")
        msg, _ = self.storage.create_message(
            thread_id="t-cur",
            message_id="m-cur-1",
            conversation_id="conv-1",
            connector_id="connector:opencli_chatgpt",
            sender="ide",
            recipient="browser",
            message_type="review.request",
            content="Test",
        )
        events = self.storage.get_events(thread_id="t-cur")
        ev1 = events[0]

        conn_id = "connector:opencli_chatgpt"

        # 1. Requires non-empty outcome
        with self.assertRaises(ValueError):
            self.storage.advance_connector_cursor(conn_id, ev1.event_id, durable_outcome="")

        # 2. Non-existent event fails
        with self.assertRaises(CursorError):
            self.storage.advance_connector_cursor(conn_id, 999999, durable_outcome="PROCESSED")

        # 3. Wrong connector event fails
        with self.assertRaises(CursorError):
            self.storage.advance_connector_cursor("connector:other", ev1.event_id, durable_outcome="PROCESSED")

        # 4. Valid advancement to ev1
        cursor = self.storage.advance_connector_cursor(conn_id, ev1.event_id, durable_outcome="PROCESSED")
        self.assertEqual(cursor.last_processed_event_id, ev1.event_id)

        # 5. Backward movement fails
        with self.assertRaises(CursorError):
            self.storage.advance_connector_cursor(conn_id, 0, durable_outcome="RESET")

    def test_concurrent_cursor_advances_preserve_maximum(self) -> None:
        self.storage.create_thread("t-cur-conc")
        conn_id = "connector:conc"

        # Create multiple events
        for i in range(1, 11):
            self.storage.create_message(
                thread_id="t-cur-conc",
                message_id=f"m-conc-{i}",
                conversation_id="conv-1",
                connector_id=conn_id,
                sender="ide",
                recipient="browser",
                message_type="review.request",
                content=f"Test {i}",
            )
        events = self.storage.get_events(thread_id="t-cur-conc", connector_id=conn_id)
        self.assertEqual(len(events), 10)
        event_ids = [ev.event_id for ev in events]

        barrier = threading.Barrier(len(event_ids))

        def advance_worker(eid: int) -> int | None:
            barrier.wait()
            st = Storage(self.db_path)
            try:
                cur = st.advance_connector_cursor(conn_id, eid, durable_outcome="BATCH_DONE")
                return cur.last_processed_event_id
            except CursorError:
                # Expected if a higher cursor was already committed by another thread
                return None

        with concurrent.futures.ThreadPoolExecutor(max_workers=len(event_ids)) as executor:
            list(executor.map(advance_worker, event_ids))

        # Check final stored cursor: MUST equal maximum event_id
        final_cursor = self.storage.get_connector_cursor(conn_id)
        self.assertIsNotNone(final_cursor)
        self.assertEqual(final_cursor.last_processed_event_id, max(event_ids))

    # -------------------------------------------------------------------------
    # 8. Exact Response Identity Binding & Mismatch Rejection
    # -------------------------------------------------------------------------
    def test_create_response_enforces_exact_identity_binding(self) -> None:
        self.storage.create_thread("t-bind")
        self.storage.create_message(
            thread_id="t-bind",
            message_id="req-bound-1",
            conversation_id="conv-exact-123",
            connector_id="connector:exact-opencli",
            sender="ide",
            recipient="browser",
            message_type="review.request",
            content="Please review",
            artifact_id="art-exact-456",
        )

        # 1. Wrong conversation_id fails closed
        with self.assertRaises(ConflictError) as ctx:
            self.storage.create_response_and_ready_event(
                thread_id="t-bind",
                response_id="resp-err-1",
                request_id="req-bound-1",
                conversation_id="conv-WRONG-UUID",
                connector_id="connector:exact-opencli",
                sender="browser",
                recipient="ide",
                content="Verdict",
                artifact_id="art-exact-456",
            )
        self.assertIn("Conversation mismatch", str(ctx.exception))

        # 2. Wrong connector_id fails closed
        with self.assertRaises(ConflictError) as ctx:
            self.storage.create_response_and_ready_event(
                thread_id="t-bind",
                response_id="resp-err-2",
                request_id="req-bound-1",
                conversation_id="conv-exact-123",
                connector_id="connector:WRONG-CONNECTOR",
                sender="browser",
                recipient="ide",
                content="Verdict",
                artifact_id="art-exact-456",
            )
        self.assertIn("Connector mismatch", str(ctx.exception))

        # 3. Wrong artifact_id fails closed
        with self.assertRaises(ConflictError) as ctx:
            self.storage.create_response_and_ready_event(
                thread_id="t-bind",
                response_id="resp-err-3",
                request_id="req-bound-1",
                conversation_id="conv-exact-123",
                connector_id="connector:exact-opencli",
                sender="browser",
                recipient="ide",
                content="Verdict",
                artifact_id="art-WRONG-HASH",
            )
        self.assertIn("Artifact mismatch", str(ctx.exception))

        # 4. Valid creation succeeds
        resp, ev, is_new = self.storage.create_response_and_ready_event(
            thread_id="t-bind",
            response_id="resp-valid-1",
            request_id="req-bound-1",
            conversation_id="conv-exact-123",
            connector_id="connector:exact-opencli",
            sender="browser",
            recipient="ide",
            content="Approved",
            artifact_id="art-exact-456",
            verdict="APPROVE",
        )
        self.assertTrue(is_new)
        self.assertEqual(resp.message_id, "resp-valid-1")
        self.assertEqual(ev.event_type, "RESPONSE_READY")

    # -------------------------------------------------------------------------
    # 9. Synchronized Response Concurrency & DB Unique Constraint
    # -------------------------------------------------------------------------
    def test_synchronized_concurrent_response_ready_atomic_creation(self) -> None:
        self.storage.create_thread("t-resp-conc")
        req_id = "req-resp-conc-1"
        self.storage.create_message(
            thread_id="t-resp-conc",
            message_id=req_id,
            conversation_id="conv-resp-conc",
            connector_id="connector:opencli",
            sender="ide",
            recipient="browser",
            message_type="review.request",
            content="Please review concurrency",
            artifact_id="art-conc",
        )

        barrier = threading.Barrier(10)

        def create_response(thread_index: int) -> tuple[str, bool]:
            barrier.wait()
            st = Storage(self.db_path)
            msg, ev, is_new = st.create_response_and_ready_event(
                thread_id="t-resp-conc",
                response_id=f"resp-{thread_index}",
                request_id=req_id,
                conversation_id="conv-resp-conc",
                connector_id="connector:opencli",
                sender="browser",
                recipient="ide",
                content="Verdict content",
                artifact_id="art-conc",
                verdict="APPROVE",
            )
            return (msg.message_id, is_new)

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(create_response, range(10)))

        # Exactly one call created the authoritative response
        new_creations = [res for res in results if res[1] is True]
        cached_returns = [res for res in results if res[1] is False]
        self.assertEqual(len(new_creations), 1)
        self.assertEqual(len(cached_returns), 9)

        winner_resp_id = new_creations[0][0]

        # Verify in database: exactly one review.response and one RESPONSE_READY event
        events = self.storage.get_events(thread_id="t-resp-conc")
        ready_events = [ev for ev in events if ev.event_type == "RESPONSE_READY"]
        self.assertEqual(len(ready_events), 1)
        self.assertEqual(ready_events[0].message_id, winner_resp_id)
        self.assertEqual(ready_events[0].payload.get("verdict"), "APPROVE")

    # -------------------------------------------------------------------------
    # 10. Transaction Rollback Integrity
    # -------------------------------------------------------------------------
    def test_transaction_failure_leaves_no_partial_records(self) -> None:
        self.storage.create_thread("t-fail")
        with self.assertRaises(ThreadIntegrityError):
            self.storage.create_response_and_ready_event(
                thread_id="t-fail",
                response_id="resp-orphan",
                request_id="non-existent-req",
                conversation_id="conv-1",
                connector_id="conn-1",
                sender="browser",
                recipient="ide",
                content="Orphan verdict",
            )

        # Verify no orphan message or event was written
        msg = self.storage.get_message("resp-orphan")
        self.assertIsNone(msg)
        events = self.storage.get_events(thread_id="t-fail")
        self.assertEqual(len(events), 0)


if __name__ == "__main__":
    unittest.main()
