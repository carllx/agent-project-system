"""
APS Message Hub - IDE Client SDK.

Features:
- Submit review request (durable ACK from hub)
- Deduplication handling
- SSE Event subscription for response notifications (no busy-polling)
- Pure standard library Python
"""

import json
import time
import urllib.request
import urllib.error
from typing import Dict, Any, Optional, Callable


class IDEClient:
    def __init__(self, hub_url: str = "http://127.0.0.1:8765"):
        self.hub_url = hub_url.rstrip("/")

    def submit_review_request(
        self,
        thread_id: str,
        message_id: str,
        artifact_id: str,
        content: str,
        sender: str = "ide:antigravity",
        recipient: str = "browser:chatgpt",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Submits review.request to hub.
        Returns immediate hub ACK response.
        """
        payload = {
            "message_id": message_id,
            "sender": sender,
            "recipient": recipient,
            "message_type": "review.request",
            "artifact_id": artifact_id,
            "content": content,
            "metadata": metadata or {}
        }
        url = f"{self.hub_url}/api/threads/{thread_id}/messages"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                elapsed = time.perf_counter() - t0
                data = json.loads(resp.read().decode("utf-8"))
                data["_elapsed_seconds"] = elapsed
                return data
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8")
            raise RuntimeError(f"HTTP {e.code}: {err_body}")

    def wait_for_response_event(
        self,
        thread_id: str,
        expected_request_id: str,
        expected_artifact_id: Optional[str] = None,
        timeout: float = 10.0
    ) -> Dict[str, Any]:
        """
        Subscribes to SSE stream until RESPONSE_READY event arrives
        binding to the expected request and artifact.
        Drives continuation strictly on RESPONSE_READY.
        No busy polling / while sleep polling is used.
        """
        url = f"{self.hub_url}/api/threads/{thread_id}/events/stream"
        req = urllib.request.Request(url, headers={"Accept": "text/event-stream"})
        t0 = time.perf_counter()

        with urllib.request.urlopen(req, timeout=timeout) as response:
            while time.perf_counter() - t0 < timeout:
                line = response.readline().decode("utf-8")
                if not line:
                    break
                line = line.strip()
                if line.startswith("data:"):
                    raw_json = line[5:].strip()
                    event = json.loads(raw_json)
                    # Block 4: Drive continuation ONLY from RESPONSE_READY for the expected request
                    if event.get("event_type") == "RESPONSE_READY":
                        event_payload = event.get("payload", {})
                        req_in_event = event_payload.get("request_id")
                        resp_msg_id = event.get("message_id") or event_payload.get("response_id")

                        # Verify exact message lookup & strict binding
                        msgs_url = f"{self.hub_url}/api/threads/{thread_id}/messages"
                        with urllib.request.urlopen(msgs_url, timeout=2.0) as m_resp:
                            m_data = json.loads(m_resp.read().decode("utf-8"))
                            for m in m_data.get("messages", []):
                                if (
                                    m.get("message_id") == resp_msg_id and
                                    m.get("reply_to") == expected_request_id and
                                    (expected_artifact_id is None or m.get("artifact_id") == expected_artifact_id)
                                ):
                                    event["_message"] = m
                                    # Block 5: measure event emission -> observation time
                                    event_created_at = event.get("created_at")
                                    if event_created_at:
                                        event["_event_delivery_latency_seconds"] = max(0.0, time.time() - event_created_at)
                                    event["_subscriber_wait_seconds"] = time.perf_counter() - t0
                                    return event
        raise TimeoutError(f"Timed out waiting for RESPONSE_READY event for request {expected_request_id}")
