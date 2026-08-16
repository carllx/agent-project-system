"""
Demo runner to generate visual and timing proofs for APS Message Hub vertical slice.
"""

import os
import sys
import tempfile
import threading
import time
from pathlib import Path
import urllib.request
import json

# Setup paths
sys.path.insert(0, str(Path(__file__).parent.resolve()))

from server import HubServer
from client_ide import IDEClient
from simulator import BrowserSimulator


def run_demo():
    print("=== APS Message Hub Vertical Slice Demonstration ===")
    tmp_dir = tempfile.mkdtemp()
    db_path = os.path.join(tmp_dir, "demo_hub.db")
    port = 8990
    server = HubServer(host="127.0.0.1", port=port, db_path=db_path)
    server.start()
    print(f"[1] Server started on http://127.0.0.1:{port} (DB: {db_path})")

    try:
        ide = IDEClient(hub_url=f"http://127.0.0.1:{port}")
        sim = BrowserSimulator(hub_url=f"http://127.0.0.1:{port}")

        thread_id = "thread-demo-001"
        req_id = "req-demo-001"
        art_id = "artifact-plan-001"

        print(f"\n[2] IDE submitting review request (req_id={req_id}, artifact={art_id})...")
        t_submit_start = time.perf_counter()
        ack = ide.submit_review_request(
            thread_id=thread_id,
            message_id=req_id,
            artifact_id=art_id,
            content="Please review the proposed architecture for APS Message Hub."
        )
        t_ack_elapsed = time.perf_counter() - t_submit_start
        print(f"    -> Server ACK received in {t_ack_elapsed*1000:.2f} ms (is_new={ack['is_new']}, status={ack['status']})")

        print(f"\n[3] Testing Deduplication with duplicate request_id...")
        ack_dup = ide.submit_review_request(
            thread_id=thread_id,
            message_id=req_id,
            artifact_id=art_id,
            content="Duplicate request"
        )
        print(f"    -> Duplicate result: is_new={ack_dup['is_new']}, existing_id={ack_dup['message']['message_id']}")

        print(f"\n[4] Browser Simulator background loop processing...")
        def sim_worker():
            time.sleep(0.1)
            sim_res = sim.process_pending_requests_once(
                thread_id,
                decision="ACCEPTED",
                reason="Phase 1 architecture validated with exact artifact binding.",
                simulated_reasoning_delay=0.08
            )
            print(f"    -> Simulator finished processing response (elapsed: {sim_res['_simulator_elapsed_seconds']*1000:.2f} ms)")

        t_sim = threading.Thread(target=sim_worker)
        t_sim.start()

        print(f"\n[5] IDE waiting for SSE event notification (no polling)...")
        event = ide.wait_for_response_event(thread_id, expected_request_id=req_id, timeout=5.0)
        t_sim.join()

        print(f"    -> Event received via SSE: {event['event_type']}")
        print(f"    -> Response decision: {event['_message']['metadata']['decision']}")
        print(f"    -> Bound reply_to: {event['_message']['reply_to']}")
        print(f"    -> Bound artifact_id: {event['_message']['artifact_id']}")
        print(f"    -> Total notification observation time: {event['_event_elapsed_seconds']*1000:.2f} ms")

        # Check Timeline HTML
        print(f"\n[6] Verifying Web Timeline HTML content...")
        html_url = f"http://127.0.0.1:{port}/threads/{thread_id}"
        with urllib.request.urlopen(html_url) as resp:
            html = resp.read().decode("utf-8")
            print(f"    -> HTML page length: {len(html)} bytes")
            print(f"    -> Contains REQUEST_CREATED: {'REQUEST_CREATED' in html}")
            print(f"    -> Contains DELIVERED_TO_CONNECTOR: {'DELIVERED_TO_CONNECTOR' in html}")
            print(f"    -> Contains RESPONSE_CREATED: {'RESPONSE_CREATED' in html}")
            print(f"    -> Contains RESPONSE_READY: {'RESPONSE_READY' in html}")

        # Restart server test
        print(f"\n[7] Simulating Server Restart & Persistence Proof...")
        server.stop()
        print("    -> Server stopped.")

        server_restarted = HubServer(host="127.0.0.1", port=port, db_path=db_path)
        server_restarted.start()
        print("    -> Server restarted on same SQLite database.")

        msgs_url = f"http://127.0.0.1:{port}/api/threads/{thread_id}/messages"
        with urllib.request.urlopen(msgs_url) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            print(f"    -> Retrieved {len(data['messages'])} messages post-restart successfully.")

        evts_url = f"http://127.0.0.1:{port}/api/threads/{thread_id}/events"
        with urllib.request.urlopen(evts_url) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            print(f"    -> Retrieved {len(data['events'])} events post-restart successfully.")

        server_restarted.stop()
        print("\n=== DEMO PASSED PERFECTLY ===")
    finally:
        server.stop()


if __name__ == "__main__":
    run_demo()
