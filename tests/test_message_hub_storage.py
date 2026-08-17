"""Focused deterministic unit and concurrency test suite for Message Hub M1 Storage."""

from __future__ import annotations

import concurrent.futures
import json
import os
import tempfile
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
    # 1 & 2. Schema Bootstrap and DB Reopen Persistence
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
    # 3 & 4. Identical Message Deduplication and Conflicting Same-ID Rejection
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
    # 5 & 6. Same-Thread Reply Hierarchy and Cross-Thread Rejection
    # -------------------------------------------------------------------------
    def test_same_thread_reply_and_cross_thread_rejection(self) -> None:
        self.storage.create_thread("thread-A")
        self.storage.create_thread("thread-B")

        req_a, _ = self.storage.create_message(
            thread_id="thread-A",
            message_id="req-A",
            conversation_id="conv-A",
            connector_id="conn-1",
            sender="ide",
            recipient="browser",
            message_type="review.request",
            content="Review A",
        )

        # Valid reply in thread-A
        reply_a, is_new = self.storage.create_message(
            thread_id="thread-A",
            message_id="note-A",
            conversation_id="conv-A",
            connector_id="conn-1",
            sender="browser",
            recipient="ide",
            message_type="review.comment",
            reply_to="req-A",
            content="Looking at it",
        )
        self.assertTrue(is_new)
        self.assertEqual(reply_a.reply_to, "req-A")

        # Invalid cross-thread reply: message in thread-B replying to req-A in thread-A
        with self.assertRaises(ThreadIntegrityError):
            self.storage.create_message(
                thread_id="thread-B",
                message_id="note-B",
                conversation_id="conv-B",
                connector_id="conn-1",
                sender="browser",
                recipient="ide",
                message_type="review.comment",
                reply_to="req-A",
                content="Cross-thread attack",
            )

        # Invalid reply to non-existent message
        with self.assertRaises(ThreadIntegrityError):
            self.storage.create_message(
                thread_id="thread-A",
                message_id="note-ghost",
                conversation_id="conv-A",
                connector_id="conn-1",
                sender="browser",
                recipient="ide",
                message_type="review.comment",
                reply_to="non-existent-parent",
                content="Ghost reply",
            )

    # -------------------------------------------------------------------------
    # 7. Reserve review.response to create_response_and_ready_event
    # -------------------------------------------------------------------------
    def test_create_message_rejects_review_response_type(self) -> None:
        self.storage.create_thread("t-resp-gate")
        self.storage.create_message(
            thread_id="t-resp-gate",
            message_id="req-gate",
            conversation_id="conv-gate",
            connector_id="conn-gate",
            sender="ide",
            recipient="browser",
            message_type="review.request",
            content="Review code",
        )

        with self.assertRaises(ValueError) as ctx:
            self.storage.create_message(
                thread_id="t-resp-gate",
                message_id="resp-unauthorized",
                conversation_id="conv-gate",
                connector_id="conn-gate",
                sender="browser",
                recipient="ide",
                message_type="review.response",
                reply_to="req-gate",
                content="Verdict bypass",
            )
        self.assertIn("Authoritative review.response", str(ctx.exception))

    # -------------------------------------------------------------------------
    # 8. First-Class Identities (connector_id & conversation_id)
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
    # 9, 10, 11 & 12. Atomic Send Claim Contention, Request Binding & Persistence
    # -------------------------------------------------------------------------
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
            content="Contend request",
        )

        def try_claim(worker_name: str) -> bool:
            st = Storage(self.db_path)
            return st.try_claim_external_send(req_id, "t-claim", worker_name)

        workers = [f"worker-{i}" for i in range(10)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(try_claim, workers))

        # Exactly one worker won the claim
        self.assertEqual(results.count(True), 1)
        self.assertEqual(results.count(False), 9)

        claim = self.storage.get_send_claim(req_id)
        self.assertIsNotNone(claim)
        self.assertIn(claim.claimed_by, workers)

        # Claim persists across DB reopen
        storage_reopen = Storage(self.db_path)
        reopened_claim = storage_reopen.get_send_claim(req_id)
        self.assertIsNotNone(reopened_claim)
        self.assertEqual(reopened_claim.claimed_by, claim.claimed_by)

        # Re-claiming returns False
        self.assertFalse(storage_reopen.try_claim_external_send(req_id, "t-claim", "worker-replay"))

    def test_send_claim_requires_real_review_request_in_correct_thread(self) -> None:
        self.storage.create_thread("t-c1")
        self.storage.create_thread("t-c2")

        self.storage.create_message(
            thread_id="t-c1",
            message_id="req-valid",
            conversation_id="conv-c1",
            connector_id="conn-c1",
            sender="ide",
            recipient="browser",
            message_type="review.request",
            content="Valid request",
        )
        self.storage.create_message(
            thread_id="t-c1",
            message_id="msg-not-req",
            conversation_id="conv-c1",
            connector_id="conn-c1",
            sender="ide",
            recipient="browser",
            message_type="system.note",
            content="Not a review request",
        )

        # Rejects non-existent request
        with self.assertRaises(ThreadIntegrityError):
            self.storage.try_claim_external_send("non-existent-req", "t-c1", "worker-1")

        # Rejects claiming in wrong thread
        with self.assertRaises(ThreadIntegrityError):
            self.storage.try_claim_external_send("req-valid", "t-c2", "worker-1")

        # Rejects claiming a message that is not a review.request
        with self.assertRaises(ThreadIntegrityError):
            self.storage.try_claim_external_send("msg-not-req", "t-c1", "worker-1")

    # -------------------------------------------------------------------------
    # 13, 14 & 15. Connector Cursor Monotonicity, Handling Outcome & Event Validation
    # -------------------------------------------------------------------------
    def test_connector_cursor_requires_durable_outcome_and_valid_event(self) -> None:
        conn_id = "connector:opencli_chatgpt"
        self.storage.create_thread("t-cursor")
        self.storage.create_message(
            thread_id="t-cursor",
            message_id="req-cursor-1",
            conversation_id="conv-1",
            connector_id=conn_id,
            sender="ide",
            recipient="browser",
            message_type="review.request",
            content="Task 1",
        )
        events = self.storage.get_events(connector_id=conn_id)
        self.assertEqual(len(events), 1)
        valid_ev_id = events[0].event_id

        # Missing handling outcome -> ValueError
        with self.assertRaises(ValueError):
            self.storage.advance_connector_cursor(conn_id, valid_ev_id, handling_outcome="")

        # Non-existent event_id -> CursorError
        with self.assertRaises(CursorError):
            self.storage.advance_connector_cursor(conn_id, 999999, handling_outcome="CLAIM_ACQUIRED")

        # Event belonging to different connector -> CursorError
        self.storage.create_message(
            thread_id="t-cursor",
            message_id="req-other-conn",
            conversation_id="conv-2",
            connector_id="connector:other_adapter",
            sender="ide",
            recipient="browser",
            message_type="review.request",
            content="Task 2",
        )
        other_events = self.storage.get_events(connector_id="connector:other_adapter")
        other_ev_id = other_events[0].event_id

        with self.assertRaises(CursorError):
            self.storage.advance_connector_cursor(conn_id, other_ev_id, handling_outcome="CLAIM_ACQUIRED")

        # Valid advancement succeeds
        cursor = self.storage.advance_connector_cursor(conn_id, valid_ev_id, handling_outcome="CLAIM_ACQUIRED")
        self.assertEqual(cursor.last_processed_event_id, valid_ev_id)

    def test_concurrent_cursor_advancement_cannot_regress(self) -> None:
        conn_id = "connector:concurrent_test"
        self.storage.create_thread("t-curr")

        event_ids: list[int] = []
        for i in range(5):
            self.storage.create_message(
                thread_id="t-curr",
                message_id=f"req-curr-{i}",
                conversation_id="conv-curr",
                connector_id=conn_id,
                sender="ide",
                recipient="browser",
                message_type="review.request",
                content=f"Task {i}",
            )
        events = self.storage.get_events(connector_id=conn_id)
        event_ids = [ev.event_id for ev in events]
        self.assertEqual(len(event_ids), 5)

        max_event_id = max(event_ids)

        def advance_worker(ev_id: int) -> None:
            st = Storage(self.db_path)
            try:
                st.advance_connector_cursor(conn_id, ev_id, handling_outcome="HANDLED")
            except CursorError:
                pass  # Slower thread trying to write smaller event_id is rejected

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            list(executor.map(advance_worker, sorted(event_ids, reverse=True)))

        final_cursor = self.storage.get_connector_cursor(conn_id)
        self.assertIsNotNone(final_cursor)
        self.assertEqual(final_cursor.last_processed_event_id, max_event_id)

    # -------------------------------------------------------------------------
    # 16, 17, 18, 19 & 20. Exact Request/Response Binding & Concurrent RESPONSE_READY
    # -------------------------------------------------------------------------
    def test_response_creation_enforces_exact_request_binding(self) -> None:
        self.storage.create_thread("t-bind")
        self.storage.create_message(
            thread_id="t-bind",
            message_id="req-target",
            conversation_id="conv-exact-uuid",
            connector_id="connector:exact_adapter",
            artifact_id="art-exact-hash",
            sender="ide",
            recipient="browser",
            message_type="review.request",
            content="Exact binding task",
        )

        # Mismatched conversation_id -> ThreadIntegrityError
        with self.assertRaises(ThreadIntegrityError) as ctx:
            self.storage.create_response_and_ready_event(
                thread_id="t-bind",
                response_id="resp-bad-conv",
                request_id="req-target",
                conversation_id="conv-WRONG-uuid",
                connector_id="connector:exact_adapter",
                artifact_id="art-exact-hash",
                sender="browser",
                recipient="ide",
                content="Verdict",
            )
        self.assertIn("conversation_id", str(ctx.exception))

        # Mismatched connector_id -> ThreadIntegrityError
        with self.assertRaises(ThreadIntegrityError) as ctx:
            self.storage.create_response_and_ready_event(
                thread_id="t-bind",
                response_id="resp-bad-conn",
                request_id="req-target",
                conversation_id="conv-exact-uuid",
                connector_id="connector:WRONG_adapter",
                artifact_id="art-exact-hash",
                sender="browser",
                recipient="ide",
                content="Verdict",
            )
        self.assertIn("connector_id", str(ctx.exception))

        # Mismatched artifact_id -> ThreadIntegrityError
        with self.assertRaises(ThreadIntegrityError) as ctx:
            self.storage.create_response_and_ready_event(
                thread_id="t-bind",
                response_id="resp-bad-art",
                request_id="req-target",
                conversation_id="conv-exact-uuid",
                connector_id="connector:exact_adapter",
                artifact_id="art-WRONG-hash",
                sender="browser",
                recipient="ide",
                content="Verdict",
            )
        self.assertIn("artifact_id", str(ctx.exception))

    def test_concurrent_response_ready_atomic_creation(self) -> None:
        self.storage.create_thread("t-resp")
        self.storage.create_message(
            thread_id="t-resp",
            message_id="req-for-resp",
            conversation_id="conv-resp",
            connector_id="connector:opencli",
            artifact_id="art-resp",
            sender="ide",
            recipient="browser",
            message_type="review.request",
            content="Please review",
        )

        def create_response(thread_index: int) -> tuple[str, bool]:
            st = Storage(self.db_path)
            msg, ev, is_new = st.create_response_and_ready_event(
                thread_id="t-resp",
                response_id=f"resp-{thread_index}",
                request_id="req-for-resp",
                conversation_id="conv-resp",
                connector_id="connector:opencli",
                artifact_id="art-resp",
                sender="browser",
                recipient="ide",
                content="Verdict content",
                verdict="APPROVE",
            )
            return (msg.message_id, is_new)

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(create_response, range(8)))

        # Exactly one call created the authoritative response
        new_creations = [res for res in results if res[1] is True]
        cached_returns = [res for res in results if res[1] is False]
        self.assertEqual(len(new_creations), 1)
        self.assertEqual(len(cached_returns), 7)

        winner_resp_id = new_creations[0][0]

        # Verify in database: exactly one review.response and one RESPONSE_READY event
        events = self.storage.get_events(thread_id="t-resp")
        ready_events = [ev for ev in events if ev.event_type == "RESPONSE_READY"]
        self.assertEqual(len(ready_events), 1)
        self.assertEqual(ready_events[0].message_id, winner_resp_id)
        self.assertEqual(ready_events[0].payload.get("verdict"), "APPROVE")

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

        msg = self.storage.get_message("resp-orphan")
        self.assertIsNone(msg)
        events = self.storage.get_events(thread_id="t-fail")
        self.assertEqual(len(events), 0)


if __name__ == "__main__":
    unittest.main()
