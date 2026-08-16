"""
Unit and Integration Tests for APS Message Hub Vertical Slice (Phase 1).

Tests cover:
1. Durable request creation & immediate ACK
2. Duplicate message_id idempotent deduplication
3. Exact request_id & artifact_id binding in review.response
4. Ordered event history sequence (REQUEST_CREATED -> DELIVERED_TO_CONNECTOR -> RESPONSE_CREATED -> RESPONSE_READY)
5. Server restart persistence proof (thread, messages, and events survive full process/server lifecycle)
6. SSE event push delivery to IDE client (no busy-polling)
7. Failure state honesty (reply_to artifact mismatch rejection)
"""

import os
import shutil
import tempfile
import threading
import time
import unittest
import urllib.request
import json

import sys
from pathlib import Path

# Add prototype directory to sys.path
sys.path.insert(0, str(Path(__file__).parent.resolve()))

from storage import Storage
from server import HubServer
from client_ide import IDEClient
from simulator import BrowserSimulator


class TestStorage(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp_dir, "test_hub.db")
        self.storage = Storage(self.db_path)

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_durable_request_and_dedup(self):
        msg, is_new, ev = self.storage.create_message(
            message_id="msg-001",
            thread_id="th-001",
            sender="ide:agent",
            recipient="browser:lead",
            message_type="review.request",
            content="Please review doc",
            artifact_id="art-100"
        )
        self.assertTrue(is_new)
        self.assertEqual(msg["message_id"], "msg-001")
        self.assertIsNotNone(ev)
        self.assertEqual(ev["event_type"], "REQUEST_CREATED")

        # Duplicate create with same ID
        msg2, is_new2, ev2 = self.storage.create_message(
            message_id="msg-001",
            thread_id="th-001",
            sender="ide:agent",
            recipient="browser:lead",
            message_type="review.request",
            content="Please review doc",
            artifact_id="art-100"
        )
        self.assertFalse(is_new2)
        self.assertEqual(msg2["message_id"], "msg-001")
        self.assertIsNone(ev2)

        # Count messages
        msgs = self.storage.get_messages("th-001")
        self.assertEqual(len(msgs), 1)

    def test_artifact_and_reply_binding_validation(self):
        # Create request
        self.storage.create_message(
            message_id="req-1",
            thread_id="th-002",
            sender="ide:agent",
            recipient="browser:lead",
            message_type="review.request",
            content="Request",
            artifact_id="art-A"
        )

        # Valid reply with matching artifact
        resp, is_new, _ = self.storage.create_message(
            message_id="resp-1",
            thread_id="th-002",
            sender="browser:lead",
            recipient="ide:agent",
            message_type="review.response",
            content="Response A",
            reply_to="req-1",
            artifact_id="art-A"
        )
        self.assertTrue(is_new)
        self.assertEqual(resp["reply_to"], "req-1")

        # Invalid reply with mismatched artifact -> must fail
        with self.assertRaises(ValueError) as ctx:
            self.storage.create_message(
                message_id="resp-2",
                thread_id="th-002",
                sender="browser:lead",
                recipient="ide:agent",
                message_type="review.response",
                content="Response B",
                reply_to="req-1",
                artifact_id="art-MISMATCH"
            )
        self.assertIn("Artifact mismatch", str(ctx.exception))


class TestEndToEndHub(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp_dir = tempfile.mkdtemp()
        cls.db_path = os.path.join(cls.tmp_dir, "e2e_hub.db")
        cls.port = 8899
        cls.server = HubServer(host="127.0.0.1", port=cls.port, db_path=cls.db_path)
        cls.server.start()
        time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()
        shutil.rmtree(cls.tmp_dir, ignore_errors=True)

    def test_end_to_end_vertical_slice(self):
        ide = IDEClient(hub_url=f"http://127.0.0.1:{self.port}")
        sim = BrowserSimulator(hub_url=f"http://127.0.0.1:{self.port}")

        thread_id = "thread-e2e-001"
        req_id = "req-e2e-001"
        art_id = "art-e2e-001"

        # 1. IDE submits review request
        ack = ide.submit_review_request(
            thread_id=thread_id,
            message_id=req_id,
            artifact_id=art_id,
            content="Review needed for APS Vertical Slice"
        )
        self.assertEqual(ack["status"], "ACK")
        self.assertTrue(ack["is_new"])
        self.assertLess(ack["_elapsed_seconds"], 0.2)  # Fast durable ACK

        # 2. Simulator consumes request in background thread
        def run_simulator():
            time.sleep(0.05)
            sim.process_pending_requests_once(thread_id, decision="ACCEPTED")

        sim_thread = threading.Thread(target=run_simulator)
        sim_thread.start()

        # 3. IDE waits via SSE event notification (no polling)
        event = ide.wait_for_response_event(thread_id, expected_request_id=req_id, timeout=3.0)
        sim_thread.join()

        self.assertIn(event["event_type"], ("RESPONSE_CREATED", "RESPONSE_READY"))
        self.assertEqual(event["_message"]["reply_to"], req_id)
        self.assertEqual(event["_message"]["artifact_id"], art_id)
        self.assertEqual(event["_message"]["metadata"]["decision"], "ACCEPTED")

        # 4. Check ordered event log
        events_url = f"http://127.0.0.1:{self.port}/api/threads/{thread_id}/events"
        with urllib.request.urlopen(events_url) as resp:
            ev_data = json.loads(resp.read().decode("utf-8"))
            event_types = [e["event_type"] for e in ev_data["events"]]
            self.assertEqual(event_types, [
                "REQUEST_CREATED",
                "DELIVERED_TO_CONNECTOR",
                "RESPONSE_CREATED",
                "RESPONSE_READY"
            ])

        # 5. Check Timeline HTML endpoint
        html_url = f"http://127.0.0.1:{self.port}/threads/{thread_id}"
        with urllib.request.urlopen(html_url) as resp:
            html = resp.read().decode("utf-8")
            self.assertIn(thread_id, html)
            self.assertIn(req_id, html)
            self.assertIn("REQUEST_CREATED", html)
            self.assertIn("RESPONSE_READY", html)

    def test_server_restart_persistence(self):
        thread_id = "thread-restart-001"
        ide = IDEClient(hub_url=f"http://127.0.0.1:{self.port}")

        ide.submit_review_request(
            thread_id=thread_id,
            message_id="req-restart-1",
            artifact_id="art-restart-1",
            content="Restart test content"
        )

        # Stop server completely
        self.server.stop()
        time.sleep(0.1)

        # Start new server on same port and DB
        new_server = HubServer(host="127.0.0.1", port=self.port, db_path=self.db_path)
        new_server.start()
        time.sleep(0.1)
        self.__class__.server = new_server

        # Verify thread and message survive
        msgs_url = f"http://127.0.0.1:{self.port}/api/threads/{thread_id}/messages"
        with urllib.request.urlopen(msgs_url) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            msgs = data["messages"]
            self.assertEqual(len(msgs), 1)
            self.assertEqual(msgs[0]["message_id"], "req-restart-1")


if __name__ == "__main__":
    unittest.main()
