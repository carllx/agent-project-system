"""
APS Message Hub - Browser Simulator Connector.

Simulates the Browser Review Lead adapter by:
1. Subscribing to review.request events on SSE or consuming thread messages
2. Emitting DELIVERED_TO_CONNECTOR event
3. Synthesizing review decision (ACCEPTED / CHANGES_REQUESTED)
4. Posting review.response message bound strictly to request_id and artifact_id
5. Emitting RESPONSE_READY event
"""

import json
import time
import urllib.request
import urllib.error
from typing import Dict, Any, Optional


class BrowserSimulator:
    def __init__(self, hub_url: str = "http://127.0.0.1:8765", connector_id: str = "simulator:browser_review_lead"):
        self.hub_url = hub_url.rstrip("/")
        self.connector_id = connector_id

    def process_pending_requests_once(
        self,
        thread_id: str,
        decision: str = "ACCEPTED",
        reason: str = "Browser Lead review approved: vertical slice validated.",
        simulated_reasoning_delay: float = 0.05
    ) -> Optional[Dict[str, Any]]:
        """
        Scans thread messages for review.request that don't have responses yet,
        and fulfills them with exact binding.
        Returns the created response payload if processed.
        """
        # Fetch thread messages
        msgs_url = f"{self.hub_url}/api/threads/{thread_id}/messages"
        with urllib.request.urlopen(msgs_url, timeout=5.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            messages = data.get("messages", [])

        # Find unanswered requests
        replied_ids = {m["reply_to"] for m in messages if m.get("reply_to")}
        for m in messages:
            if m["message_type"] == "review.request" and m["message_id"] not in replied_ids:
                req_id = m["message_id"]
                artifact_id = m["artifact_id"]

                t0 = time.perf_counter()
                # 1. Record DELIVERED_TO_CONNECTOR event
                self._post_event(thread_id, "DELIVERED_TO_CONNECTOR", req_id, {
                    "connector": self.connector_id,
                    "request_id": req_id,
                    "artifact_id": artifact_id
                })

                if simulated_reasoning_delay > 0:
                    time.sleep(simulated_reasoning_delay)

                # 2. Post review.response
                resp_msg_id = f"resp-{req_id}"
                content = f"VERDICT: {decision}\n\nReview Notes:\n{reason}\nBound Artifact: {artifact_id}"
                resp_payload = {
                    "message_id": resp_msg_id,
                    "sender": self.connector_id,
                    "recipient": m["sender"],
                    "message_type": "review.response",
                    "reply_to": req_id,
                    "artifact_id": artifact_id,
                    "content": content,
                    "metadata": {
                        "decision": decision,
                        "reviewed_artifact": artifact_id
                    },
                    "status": "COMPLETED"
                }

                url = f"{self.hub_url}/api/threads/{thread_id}/messages"
                req = urllib.request.Request(
                    url,
                    data=json.dumps(resp_payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=5.0) as r_resp:
                    created_data = json.loads(r_resp.read().decode("utf-8"))

                # 3. Post RESPONSE_READY event
                self._post_event(thread_id, "RESPONSE_READY", resp_msg_id, {
                    "response_id": resp_msg_id,
                    "request_id": req_id,
                    "decision": decision,
                    "artifact_id": artifact_id
                })
                elapsed = time.perf_counter() - t0
                created_data["_simulator_elapsed_seconds"] = elapsed
                return created_data
        return None

    def _post_event(self, thread_id: str, event_type: str, message_id: str, payload: Dict[str, Any]):
        url = f"{self.hub_url}/api/threads/{thread_id}/events"
        data = {
            "event_type": event_type,
            "message_id": message_id,
            "payload": payload
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            return json.loads(resp.read().decode("utf-8"))
