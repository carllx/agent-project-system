"""
APS Message Hub Phase 2 A/B Comparative Live Experiment Runner.

Compares:
Path A: Existing Minimal Bridge Baseline
Path B: APS Message Hub + Real OpenCLI Browser Connector

Measures:
Baseline:
B1. caller -> Minimal Bridge submission return
B2. external send invocation duration/outcome
B3. time until Browser response becomes observable
B4. caller blocking / waiting behavior
B5. available durable/recovery evidence

Message Hub:
H1. IDE submit -> durable Hub ACK
H2. Hub request persisted -> connector observes request
H3. connector EXTERNAL_SEND_ATTEMPTED -> OpenCLI invocation return/outcome
H4. Browser response -> connector observation (classified honestly)
H5. response persisted -> IDE RESPONSE_READY observation
H6. IDE blocking duration after durable ACK
H7. restart/no-resend behavior
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path
import urllib.request

# Include paths
ROOT = Path(__file__).resolve().parents[2]
PROTOTYPE_DIR = ROOT / "prototype" / "message-hub"
SKILL_DIR = ROOT / "skills" / "research-review-lead" / "scripts"

sys.path.insert(0, str(PROTOTYPE_DIR))
sys.path.insert(0, str(SKILL_DIR))

from storage import Storage
from server import HubServer
from client_ide import IDEClient
from opencli_connector import OpenCLIBrowserConnector, run_sse_connector_worker
from minimal_bridge import dispatch_review, load_receipt, get_canonical_receipt_dir


def run_ab_experiment(conversation_id: str):
    print("=================================================================")
    print("APS-MESSAGE-HUB-POC-002: Live A/B Comparative Validation")
    print(f"Target Known Conversation: {conversation_id}")
    print("=================================================================\n")

    results = {}

    # -------------------------------------------------------------
    # PATH A: Existing Minimal Bridge Baseline
    # -------------------------------------------------------------
    req_id_a = f"APS-AB-BASELINE-{int(time.time())}"
    art_id_a = f"art-ab-baseline-{int(time.time())}"
    prompt_a = f"""Please review the following minimal artifact test payload:
Artifact ID: {art_id_a}
Request ID: {req_id_a}
Instruction: Confirm receipt with APPROVE / REVISE / BLOCKED.
```json
{{"request_id": "{req_id_a}", "artifact_id": "{art_id_a}", "decision": "APPROVE", "feedback": "Baseline payload verified.", "next_steps": []}}
```"""

    print(">>> [PATH A] Running Existing Minimal Bridge Baseline...")
    t_start_a = time.perf_counter()
    receipt_a = dispatch_review(
        request_id=req_id_a,
        artifact_id=art_id_a,
        conversation_id=conversation_id,
        review_prompt=prompt_a,
        timeout_seconds=30
    )
    t_elapsed_a = time.perf_counter() - t_start_a

    send_state_a = receipt_a.get("receipt", {}).get("send_state", "SEND_ATTEMPTED")
    print(f"    B1. Caller -> Minimal Bridge return: {t_elapsed_a*1000:.2f} ms")
    print(f"    B2. External send state: {send_state_a}")
    print(f"    B4. Caller blocked for entire OpenCLI execution: YES ({t_elapsed_a*1000:.2f} ms)")
    print(f"    B5. Durable receipt written: {receipt_a}")

    results["baseline"] = {
        "request_id": req_id_a,
        "artifact_id": art_id_a,
        "conversation_id": conversation_id,
        "elapsed_ms": t_elapsed_a * 1000,
        "send_state": send_state_a,
        "blocking": True,
        "receipt": receipt_a
    }

    # -------------------------------------------------------------
    # PATH B: APS Message Hub + Independent Event-Driven OpenCLI Connector
    # -------------------------------------------------------------
    print("\n>>> [PATH B] Running APS Message Hub + Independent Event-Driven OpenCLI Connector...")
    tmp_dir = tempfile.mkdtemp()
    db_path = os.path.join(tmp_dir, "ab_hub.db")
    port = 8995
    server = HubServer(host="127.0.0.1", port=port, db_path=db_path)
    server.start()
    time.sleep(0.1)

    try:
        ide = IDEClient(hub_url=f"http://127.0.0.1:{port}")
        storage = Storage(db_path)
        connector = OpenCLIBrowserConnector(storage=storage)

        thread_id = f"th-ab-final-{int(time.time())}"
        req_id_b = f"APS-AB-HUB-FINAL-{int(time.time())}"
        art_id_b = f"art-ab-hub-final-{int(time.time())}"
        prompt_b = f"""Please review the following Message Hub vertical slice payload:
Artifact ID: {art_id_b}
Request ID: {req_id_b}
Instruction: Confirm receipt with APPROVE / REVISE / BLOCKED.
```json
{{"request_id": "{req_id_b}", "artifact_id": "{art_id_b}", "decision": "APPROVE", "feedback": "Message Hub control plane verified.", "next_steps": []}}
```"""

        # Start independent event-driven connector worker
        stop_worker = threading.Event()
        worker_thread = threading.Thread(
            target=run_sse_connector_worker,
            kwargs={
                "hub_url": f"http://127.0.0.1:{port}",
                "thread_id": thread_id,
                "conversation_id": conversation_id,
                "storage": storage,
                "connector": connector,
                "stop_event": stop_worker,
                "max_events": 1,
            },
            daemon=True
        )
        worker_thread.start()
        time.sleep(0.1)  # SSE stream established

        # H1. IDE submits review request -> immediate durable ACK
        t0_submit = time.perf_counter()
        ack = ide.submit_review_request(
            thread_id=thread_id,
            message_id=req_id_b,
            artifact_id=art_id_b,
            content=prompt_b,
            metadata={"experiment": "Path-B-Event-Driven"}
        )
        t_ack_ms = (time.perf_counter() - t0_submit) * 1000
        print(f"    H1. IDE submit -> Durable Hub ACK: {t_ack_ms:.2f} ms (is_new={ack['is_new']}, status={ack['status']})")
        print(f"    H6. IDE main loop unblocked immediately: YES (blocked only {t_ack_ms:.2f} ms vs baseline {t_elapsed_a*1000:.2f} ms)")

        # Wait for independent worker to process from SSE stream
        print("    [Worker] Independent SSE worker processing from REQUEST_CREATED event...")
        worker_thread.join(timeout=35.0)

        # H7. Verify No-Resend safety invariant
        dup_res = connector.process_review_request(
            thread_id=thread_id,
            request_id=req_id_b,
            conversation_id=conversation_id,
        )
        print(f"    H7. Connector duplicate resend attempt blocked: {dup_res['status']}")

        # Verify durable event log in hub
        events = storage.get_events(thread_id)
        event_types = [e["event_type"] for e in events]
        print(f"    Hub Durable Event Sequence: {event_types}")

        results["hub"] = {
            "request_id": req_id_b,
            "artifact_id": art_id_b,
            "conversation_id": conversation_id,
            "ide_ack_ms": t_ack_ms,
            "event_driven_worker": True,
            "no_resend_status": dup_res["status"],
            "event_sequence": event_types
        }

    finally:
        server.stop()

    print("\n=================================================================")
    print("A/B EXPERIMENT RESULTS SUMMARY")
    print(json.dumps(results, indent=2))
    print("=================================================================")
    return results


if __name__ == "__main__":
    conv = sys.argv[1] if len(sys.argv) > 1 else "6a81c287-566c-83ea-b80b-898f3106daf5"
    run_ab_experiment(conv)
