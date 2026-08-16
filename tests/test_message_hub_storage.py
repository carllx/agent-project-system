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
            message_id="resp-A",
            conversation_id="conv-A",
            connector_id="conn-1",
            sender="browser",
            recipient="ide",
            message_type="review.response",
            reply_to="req-A",
            content="Approved",
        )
        self.assertTrue(is_new)
        self.assertEqual(reply_a.reply_to, "req-A")

        # Invalid cross-thread reply: message in thread-B replying to req-A in thread-A
        with self.assertRaises(ThreadIntegrityError):
            self.storage.create_message(
                thread_id="thread-B",
                message_id="resp-B",
                conversation_id="conv-B",
                connector_id="conn-1",
                sender="browser",
                recipient="ide",
                message_type="review.response",
                reply_to="req-A",
                content="Cross-thread attack",
            )

        # Invalid reply to non-existent message
        with self.assertRaises(ThreadIntegrityError):
            self.storage.create_message(
                thread_id="thread-A",
                message_id="resp-ghost",
                conversation_id="conv-A",
                connector_id="conn-1",
                sender="browser",
                recipient="ide",
                message_type="review.response",
                reply_to="non-existent-parent",
                content="Ghost reply",
            )

    # -------------------------------------------------------------------------
    # 7 & 8. First-Class Identities (connector_id & conversation_id)
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

        # Validates rejection on empty first-class fields
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
    # 9, 10, 11 & 12. Atomic Send Claim Contention & Persistence
    # -------------------------------------------------------------------------
    def test_atomic_send_claim_contention_and_restart_persistence(self) -> None:
        self.storage.create_thread("t-claim")
        req_id = "req-contend-001"

        def try_claim(worker_name: str) -> bool:
            # Independent Storage instance (independent SQLite connection)
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

        # Crash-after-claim distinction: send_claim exists, but no response message yet
        resp = storage_reopen.get_message("resp-for-req-contend-001")
        self.assertIsNone(resp)
        # Attempting to re-claim returns False (no permission for second external send)
        self.assertFalse(storage_reopen.try_claim_external_send(req_id, "t-claim", "worker-replay"))

    # -------------------------------------------------------------------------
    # 13, 14 & 15. Connector Cursor Persistence and Monotonicity
    # -------------------------------------------------------------------------
    def test_connector_cursor_persistence_and_monotonicity(self) -> None:
        conn_id = "connector:opencli_chatgpt"
        cursor = self.storage.advance_connector_cursor(conn_id, 10)
        self.assertEqual(cursor.last_processed_event_id, 10)

        # Advance forward to 25
        cursor2 = self.storage.advance_connector_cursor(conn_id, 25)
        self.assertEqual(cursor2.last_processed_event_id, 25)

        # Reopen DB and check persistence
        storage2 = Storage(self.db_path)
        fetched_cursor = storage2.get_connector_cursor(conn_id)
        self.assertIsNotNone(fetched_cursor)
        self.assertEqual(fetched_cursor.last_processed_event_id, 25)

        # Moving backwards is rejected
        with self.assertRaises(CursorError):
            storage2.advance_connector_cursor(conn_id, 20)

        # Advancing to same id (idempotent checkpointing) succeeds
        cursor_same = storage2.advance_connector_cursor(conn_id, 25)
        self.assertEqual(cursor_same.last_processed_event_id, 25)

    # -------------------------------------------------------------------------
    # 16, 17, 18, 19 & 20. Concurrent RESPONSE_READY & Atomic Transaction
    # -------------------------------------------------------------------------
    def test_concurrent_response_ready_atomic_creation(self) -> None:
        self.storage.create_thread("t-resp")
        self.storage.create_message(
            thread_id="t-resp",
            message_id="req-for-resp",
            conversation_id="conv-resp",
            connector_id="connector:opencli",
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
        # Attempt to create response for a non-existent request_id
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
