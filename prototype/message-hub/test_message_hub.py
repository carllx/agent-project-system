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
            artifact_id="art-100",
            metadata={"priority": "high"}
        )
        self.assertTrue(is_new)
        self.assertEqual(msg["message_id"], "msg-001")
        self.assertIsNotNone(ev)
        self.assertEqual(ev["event_type"], "REQUEST_CREATED")

        # Duplicate create with exact same authoritative fields -> dedup success
        msg2, is_new2, ev2 = self.storage.create_message(
            message_id="msg-001",
            thread_id="th-001",
            sender="ide:agent",
            recipient="browser:lead",
            message_type="review.request",
            content="Please review doc",
            artifact_id="art-100",
            metadata={"priority": "high"}
        )
        self.assertFalse(is_new2)
        self.assertEqual(msg2["message_id"], "msg-001")
        self.assertIsNone(ev2)

        # Count messages
        msgs = self.storage.get_messages("th-001")
        self.assertEqual(len(msgs), 1)

    def test_conflicting_same_id_rejection(self):
        # 1. Create original message
        self.storage.create_message(
            message_id="msg-conflict-1",
            thread_id="th-conflict",
            sender="ide:agent",
            recipient="browser:lead",
            message_type="review.request",
            content="Original content",
            artifact_id="art-orig",
            metadata={"meta_key": 1}
        )

        # 2. Conflict: changed content
        with self.assertRaises(ValueError) as ctx:
            self.storage.create_message(
                message_id="msg-conflict-1",
                thread_id="th-conflict",
                sender="ide:agent",
                recipient="browser:lead",
                message_type="review.request",
                content="Altered content",
                artifact_id="art-orig",
                metadata={"meta_key": 1}
            )
        self.assertIn("Conflict: message_id 'msg-conflict-1' already exists", str(ctx.exception))

        # 3. Conflict: changed artifact_id
        with self.assertRaises(ValueError) as ctx:
            self.storage.create_message(
                message_id="msg-conflict-1",
                thread_id="th-conflict",
                sender="ide:agent",
                recipient="browser:lead",
                message_type="review.request",
                content="Original content",
                artifact_id="art-different",
                metadata={"meta_key": 1}
            )
        self.assertIn("Conflict", str(ctx.exception))

        # 4. Conflict: changed metadata
        with self.assertRaises(ValueError) as ctx:
            self.storage.create_message(
                message_id="msg-conflict-1",
                thread_id="th-conflict",
                sender="ide:agent",
                recipient="browser:lead",
                message_type="review.request",
                content="Original content",
                artifact_id="art-orig",
                metadata={"meta_key": 2}
            )
        self.assertIn("Conflict", str(ctx.exception))

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

        # Valid reply with matching artifact and same thread
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

    def test_cross_thread_reply_rejection(self):
        # Create request in Thread A
        self.storage.create_message(
            message_id="req-thread-A",
            thread_id="thread-A",
            sender="ide:agent",
            recipient="browser:lead",
            message_type="review.request",
            content="Request in Thread A",
            artifact_id="art-shared"
        )

        # Response attempted in Thread B pointing to Thread A request -> must fail closed
        with self.assertRaises(ValueError) as ctx:
            self.storage.create_message(
                message_id="resp-thread-B",
                thread_id="thread-B",
                sender="browser:lead",
                recipient="ide:agent",
                message_type="review.response",
                content="Attempted cross-thread reply",
                reply_to="req-thread-A",
                artifact_id="art-shared"
            )
        self.assertIn("Cross-thread reply rejected", str(ctx.exception))


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

        # 3. IDE waits via SSE event notification (strictly on RESPONSE_READY)
        event = ide.wait_for_response_event(thread_id, expected_request_id=req_id, expected_artifact_id=art_id, timeout=4.0)
        sim_thread.join()

        self.assertEqual(event["event_type"], "RESPONSE_READY")
        self.assertEqual(event["_message"]["reply_to"], req_id)
        self.assertEqual(event["_message"]["artifact_id"], art_id)
        self.assertEqual(event["_message"]["metadata"]["decision"], "ACCEPTED")
        self.assertIn("_event_delivery_latency_seconds", event)

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

    def test_sse_no_loss_handoff_under_race(self):
        """
        Deterministic regression test proving that events emitted exactly while
        the SSE subscriber transitions from historical playback to live listener
        are never missed or dropped.
        """
        thread_id = "thread-sse-race"
        ide = IDEClient(hub_url=f"http://127.0.0.1:{self.port}")

        # 1. Create initial historical event
        ack1 = ide.submit_review_request(
            thread_id=thread_id,
            message_id="req-race-1",
            artifact_id="art-race-1",
            content="Historical request 1"
        )
        self.assertTrue(ack1["is_new"])

        # 2. Connect to SSE stream
        stream_url = f"http://127.0.0.1:{self.port}/api/threads/{thread_id}/events/stream"
        req = urllib.request.Request(stream_url, headers={"Accept": "text/event-stream"})
        response = urllib.request.urlopen(req, timeout=5.0)

        # 3. Read first event (historical)
        first_line = response.readline().decode("utf-8").strip()
        while not first_line.startswith("data:"):
            first_line = response.readline().decode("utf-8").strip()
        first_ev = json.loads(first_line[5:].strip())
        self.assertEqual(first_ev["event_type"], "REQUEST_CREATED")

        # 4. Immediately emit a live event concurrently
        self.server.storage.record_event(
            thread_id=thread_id,
            event_type="LIVE_EMITTED_EVENT",
            payload={"marker": "no-loss-proof"}
        )
        # Broadcast to server listeners
        ev_live = self.server.storage.get_events(thread_id)[-1]
        self.server.broadcast_event(thread_id, ev_live)

        # 5. Read stream to confirm live event is delivered with zero loss
        second_line = response.readline().decode("utf-8").strip()
        while not second_line.startswith("data:"):
            second_line = response.readline().decode("utf-8").strip()
        second_ev = json.loads(second_line[5:].strip())
        self.assertEqual(second_ev["event_type"], "LIVE_EMITTED_EVENT")
        self.assertEqual(second_ev["payload"]["marker"], "no-loss-proof")

        response.close()

    def test_server_restart_persistence(self):
        thread_id = "thread-restart-001"
        ide = IDEClient(hub_url=f"http://127.0.0.1:{self.port}")

        ide.submit_review_request(
            thread_id=thread_id,
            message_id="req-restart-1",
            artifact_id="art-restart-1",
            content="Restart test content"
        )

        # Record explicit event
        self.server.storage.record_event(
            thread_id=thread_id,
            event_type="PRE_RESTART_EVENT",
            payload={"durable": True}
        )

        # Stop server completely
        self.server.stop()
        time.sleep(0.1)

        # Start new server on same port and DB
        new_server = HubServer(host="127.0.0.1", port=self.port, db_path=self.db_path)
        new_server.start()
        time.sleep(0.1)
        self.__class__.server = new_server

        # 1. Verify messages survive restart
        msgs_url = f"http://127.0.0.1:{self.port}/api/threads/{thread_id}/messages"
        with urllib.request.urlopen(msgs_url) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            msgs = data["messages"]
            self.assertEqual(len(msgs), 1)
            self.assertEqual(msgs[0]["message_id"], "req-restart-1")

        # 2. Verify events survive restart
        evts_url = f"http://127.0.0.1:{self.port}/api/threads/{thread_id}/events"
        with urllib.request.urlopen(evts_url) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            events = data["events"]
            event_types = [e["event_type"] for e in events]
            self.assertIn("REQUEST_CREATED", event_types)
            self.assertIn("PRE_RESTART_EVENT", event_types)
            self.assertEqual(len(events), 2)


from opencli_connector import OpenCLIBrowserConnector


class TestOpenCLIBrowserConnector(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp_dir, "test_connector.db")
        self.storage = Storage(self.db_path)

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_connector_consumes_durable_request_and_records_states(self):
        thread_id = "th-conn-1"
        req_id = "req-conn-1"
        art_id = "art-conn-1"
        conv_id = "conv-12345"

        # 1. Create request in storage
        self.storage.create_message(
            message_id=req_id,
            thread_id=thread_id,
            sender="ide:agent",
            recipient="browser:lead",
            message_type="review.request",
            content="Please review module",
            artifact_id=art_id,
        )

        calls = []
        def fake_runner(cmd, timeout):
            calls.append((cmd, timeout))
            return 0, '{"Status": "Success"}', ""

        connector = OpenCLIBrowserConnector(storage=self.storage, opencli_runner=fake_runner)
        res = connector.process_review_request(thread_id, req_id, conv_id)

        self.assertEqual(res["status"], "EXTERNAL_SEND_COMPLETED")
        self.assertEqual(len(calls), 1)
        self.assertIn("--conversation", calls[0][0])
        self.assertIn(conv_id, calls[0][0])

        # Verify durable event sequence
        events = self.storage.get_events(thread_id)
        event_types = [e["event_type"] for e in events]
        self.assertEqual(event_types, [
            "REQUEST_CREATED",
            "CONNECTOR_ACCEPTED",
            "EXTERNAL_SEND_ATTEMPTED",
            "EXTERNAL_SEND_COMPLETED",
        ])

    def test_no_resend_on_duplicate_or_restart(self):
        thread_id = "th-conn-2"
        req_id = "req-conn-2"
        conv_id = "conv-12345"

        self.storage.create_message(
            message_id=req_id,
            thread_id=thread_id,
            sender="ide:agent",
            recipient="browser:lead",
            message_type="review.request",
            content="Please review module",
            artifact_id="art-2",
        )

        calls = []
        def fake_runner(cmd, timeout):
            calls.append(cmd)
            return 0, "ok", ""

        connector = OpenCLIBrowserConnector(storage=self.storage, opencli_runner=fake_runner)
        res1 = connector.process_review_request(thread_id, req_id, conv_id)
        self.assertEqual(res1["status"], "EXTERNAL_SEND_COMPLETED")
        self.assertEqual(len(calls), 1)

        # Re-invoke on same connector -> must refuse
        res2 = connector.process_review_request(thread_id, req_id, conv_id)
        self.assertEqual(res2["status"], "SKIPPED_ALREADY_ATTEMPTED")
        self.assertEqual(len(calls), 1)

        # Simulate connector process restart with new instance against same DB
        connector_restarted = OpenCLIBrowserConnector(storage=Storage(self.db_path), opencli_runner=fake_runner)
        res3 = connector_restarted.process_review_request(thread_id, req_id, conv_id)
        self.assertEqual(res3["status"], "SKIPPED_ALREADY_ATTEMPTED")
        self.assertEqual(len(calls), 1)  # STILL 1 call

    def test_timeout_becomes_unknown_and_never_retries(self):
        thread_id = "th-conn-3"
        req_id = "req-conn-3"
        conv_id = "conv-timeout"

        self.storage.create_message(
            message_id=req_id,
            thread_id=thread_id,
            sender="ide:agent",
            recipient="browser:lead",
            message_type="review.request",
            content="Please review module",
            artifact_id="art-3",
        )

        calls = []
        def fake_timing_out_runner(cmd, timeout):
            calls.append(cmd)
            return 124, "", "Command timed out"

        connector = OpenCLIBrowserConnector(storage=self.storage, opencli_runner=fake_timing_out_runner)
        res = connector.process_review_request(thread_id, req_id, conv_id)

        self.assertEqual(res["status"], "EXTERNAL_SEND_UNKNOWN")
        self.assertEqual(len(calls), 1)

        events = self.storage.get_events(thread_id)
        event_types = [e["event_type"] for e in events]
        self.assertIn("EXTERNAL_SEND_ATTEMPTED", event_types)
        self.assertIn("EXTERNAL_SEND_UNKNOWN", event_types)

        # Subsequent execution MUST NOT retry
        res_retry = connector.process_review_request(thread_id, req_id, conv_id)
        self.assertEqual(res_retry["status"], "SKIPPED_ALREADY_ATTEMPTED")
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
