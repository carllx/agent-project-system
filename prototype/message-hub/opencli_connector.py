"""
APS Message Hub - Real OpenCLI Browser Connector (Phase 2).

Responsibilities:
1. Consume durable review.request from Message Hub for a given thread.
2. Atomically acquire external-send claim in SQLite before invoking OpenCLI.
3. Enforce strict no-resend: exactly one worker acquires claim; all others return SKIPPED_ALREADY_ATTEMPTED.
4. Invocations timeout -> EXTERNAL_SEND_UNKNOWN (failure-honest, never retry).
5. Ingest browser responses strictly parsing Browser review decision (APPROVE | REVISE | BLOCKED)
   and validating exact request_id, artifact_id, and conversation provenance. Caller-supplied approval is rejected.
6. Provide event-driven SSE connector runner for decoupled continuation.
"""

from __future__ import annotations

import json
import re
import subprocess
import time
import urllib.request
from typing import Any, Callable, Dict, Optional

from storage import Storage

LEGAL_DECISIONS = {"APPROVE", "REVISE", "BLOCKED"}


def parse_strict_browser_response(
    raw_text: str,
    expected_request_id: str,
    expected_artifact_id: str,
) -> Dict[str, Any]:
    """
    Parses and strictly verifies Browser Review Lead response JSON.
    Rejects malformed JSON, mismatched request_id / artifact_id, and invalid decisions.
    """
    if not isinstance(raw_text, str) or not raw_text.strip():
        raise ValueError("Browser response is empty or not text")

    exp_req = expected_request_id.strip()
    exp_art = expected_artifact_id.strip()
    text = raw_text.strip()

    # Match fenced JSON blocks
    fenced_blocks = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    text_without_fences = re.sub(r"```(?:json)?\s*\{.*?\}\s*```", "", text, flags=re.DOTALL)
    bare_objects = re.findall(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text_without_fences, re.DOTALL)

    if len(fenced_blocks) == 1:
        if len(bare_objects) > 0:
            raise ValueError("Ambiguous response: found fenced JSON block and bare JSON object")
        candidate_json = fenced_blocks[0]
    elif len(fenced_blocks) > 1:
        raise ValueError(f"Ambiguous response: found {len(fenced_blocks)} fenced JSON blocks")
    else:
        if len(bare_objects) == 1:
            candidate_json = bare_objects[0]
        elif len(bare_objects) > 1:
            raise ValueError(f"Ambiguous response: found {len(bare_objects)} bare JSON objects")
        else:
            raise ValueError("No valid JSON review verdict found in Browser response text")

    try:
        parsed = json.loads(candidate_json)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Malformed JSON in browser response: {exc}") from exc

    if not isinstance(parsed, dict):
        raise ValueError("Browser response JSON must be a single JSON object")

    req_id = parsed.get("request_id")
    if not isinstance(req_id, str) or req_id != exp_req:
        raise ValueError(f"request_id mismatch: expected '{exp_req}', got '{req_id}'")

    art_id = parsed.get("artifact_id")
    if not isinstance(art_id, str) or art_id != exp_art:
        raise ValueError(f"artifact_id mismatch: expected '{exp_art}', got '{art_id}'")

    decision = parsed.get("decision")
    if decision not in LEGAL_DECISIONS:
        raise ValueError(f"Invalid decision '{decision}'. Must be one of {sorted(LEGAL_DECISIONS)}")

    feedback = parsed.get("feedback")
    if not isinstance(feedback, str) or not feedback.strip():
        raise ValueError("feedback must be a non-empty string in browser response")

    next_steps = parsed.get("next_steps") or []
    if not isinstance(next_steps, list):
        raise ValueError("next_steps must be a list of strings")

    return {
        "request_id": exp_req,
        "artifact_id": exp_art,
        "decision": decision,
        "feedback": feedback.strip(),
        "next_steps": [str(s).strip() for s in next_steps],
    }


class OpenCLIBrowserConnector:
    def __init__(
        self,
        storage: Storage,
        connector_id: str = "connector:opencli_chatgpt",
        opencli_runner: Optional[Callable[[list[str], float], tuple[int, str, str]]] = None,
        default_timeout: float = 30.0,
    ):
        self.storage = storage
        self.connector_id = connector_id
        self.opencli_runner = opencli_runner or self._default_opencli_runner
        self.default_timeout = default_timeout

    @staticmethod
    def _resolve_opencli_command() -> list[str]:
        import shutil, re, os
        from pathlib import Path
        env_exe = os.environ.get("OPENCLI_EXECUTABLE")
        if env_exe:
            return [env_exe]
        if os.name == "nt":
            for candidate in ("opencli.cmd", "opencli.ps1"):
                found = shutil.which(candidate)
                if found:
                    shim = Path(found)
                    try:
                        text = shim.read_text(encoding="utf-8", errors="replace")
                        m = re.search(r'node_modules[\\/](?:@[^\\/\s"\']+[\\/])?[^\\/\s"\']+[\\/][^"\'\r\n]*?\.js', text)
                        if m:
                            entry = (shim.parent / m.group(0)).resolve()
                            node = shutil.which("node.exe") or shutil.which("node") or "node"
                            if entry.is_file():
                                return [node, str(entry)]
                    except Exception:
                        pass
        resolved = shutil.which("opencli")
        return [resolved] if resolved else ["opencli"]

    @classmethod
    def _default_opencli_runner(cls, cmd: list[str], timeout: float) -> tuple[int, str, str]:
        try:
            base_cmd = cls._resolve_opencli_command()
            if cmd and cmd[0] == "opencli":
                full_cmd = [*base_cmd, *cmd[1:]]
            else:
                full_cmd = [*base_cmd, *cmd]

            res = subprocess.run(
                full_cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
            )
            return res.returncode, res.stdout, res.stderr
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout or ""
            if isinstance(stdout, bytes):
                stdout = stdout.decode("utf-8", errors="replace")
            stderr = exc.stderr or ""
            if isinstance(stderr, bytes):
                stderr = stderr.decode("utf-8", errors="replace")
            return 124, stdout, stderr + f"\nCommand timed out after {timeout}s"
        except Exception as exc:
            return 1, "", str(exc)

    def process_review_request(
        self,
        thread_id: str,
        request_id: str,
        expected_conversation_id: str,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Atomically claims and processes one specific review request durably with at most one external send attempt.
        Validates request's durable conversation_id before acquiring claim or invoking runner.
        """
        cmd_timeout = timeout or self.default_timeout

        # Find the message
        messages = self.storage.get_messages(thread_id)
        target_msg = None
        for m in messages:
            if m["message_id"] == request_id:
                target_msg = m
                break

        if not target_msg:
            raise ValueError(f"Request message '{request_id}' not found in thread '{thread_id}'")

        if target_msg["message_type"] != "review.request":
            raise ValueError(f"Message '{request_id}' is not a review.request (type: {target_msg['message_type']})")

        # 1. DURABLE REQUEST CONVERSATION BINDING CHECK:
        # Request must durably own its conversation_id in metadata
        req_meta = target_msg.get("metadata") or {}
        req_conv_id = req_meta.get("conversation_id")
        if not req_conv_id:
            raise ValueError(f"Request '{request_id}' is missing required durable conversation_id binding in metadata")

        if req_conv_id != expected_conversation_id:
            raise ValueError(
                f"Conversation binding mismatch: request '{request_id}' is bound to '{req_conv_id}', but runtime context is '{expected_conversation_id}'"
            )

        artifact_id = target_msg.get("artifact_id")

        # 2. ATOMIC SQLite CLAIM: exactly one worker acquires claim for request_id
        acquired = self.storage.try_claim_external_send(
            thread_id=thread_id,
            request_id=request_id,
            claimed_by=self.connector_id,
        )
        if not acquired:
            return {
                "status": "SKIPPED_ALREADY_ATTEMPTED",
                "request_id": request_id,
                "message": "External send claim already held for this request. Refusing to resend.",
            }

        # 3. Record CONNECTOR_ACCEPTED
        self.storage.record_event(
            thread_id=thread_id,
            event_type="CONNECTOR_ACCEPTED",
            message_id=request_id,
            payload={
                "connector": self.connector_id,
                "request_id": request_id,
                "artifact_id": artifact_id,
                "conversation_id": req_conv_id,
            },
        )

        # 4. Durably record EXTERNAL_SEND_ATTEMPTED BEFORE invoking OpenCLI
        t_attempt = time.time()
        self.storage.record_event(
            thread_id=thread_id,
            event_type="EXTERNAL_SEND_ATTEMPTED",
            message_id=request_id,
            payload={
                "connector": self.connector_id,
                "request_id": request_id,
                "artifact_id": artifact_id,
                "conversation_id": req_conv_id,
                "attempted_at": t_attempt,
            },
        )

        # 5. Invoke OpenCLI send (submit-only)
        prompt_content = target_msg["content"]
        cmd = [
            "opencli",
            "chatgpt",
            "send",
            prompt_content,
            "--conversation",
            req_conv_id,
            "-f",
            "json",
        ]

        t0 = time.perf_counter()
        returncode, stdout, stderr = self.opencli_runner(cmd, cmd_timeout)
        elapsed = time.perf_counter() - t0

        if returncode == 124:
            # Timed out -> failure-honest UNKNOWN
            self.storage.record_event(
                thread_id=thread_id,
                event_type="EXTERNAL_SEND_UNKNOWN",
                message_id=request_id,
                payload={
                    "connector": self.connector_id,
                    "request_id": request_id,
                    "conversation_id": req_conv_id,
                    "reason": "TimeoutExpired",
                    "elapsed_seconds": elapsed,
                    "stderr": stderr,
                },
            )
            return {
                "status": "EXTERNAL_SEND_UNKNOWN",
                "request_id": request_id,
                "elapsed_seconds": elapsed,
                "error": "OpenCLI send timed out; actual browser state is UNKNOWN",
            }

        if returncode != 0:
            self.storage.record_event(
                thread_id=thread_id,
                event_type="EXTERNAL_SEND_FAILED",
                message_id=request_id,
                payload={
                    "connector": self.connector_id,
                    "request_id": request_id,
                    "conversation_id": req_conv_id,
                    "returncode": returncode,
                    "elapsed_seconds": elapsed,
                    "stderr": stderr,
                },
            )
            return {
                "status": "EXTERNAL_SEND_FAILED",
                "request_id": request_id,
                "returncode": returncode,
                "elapsed_seconds": elapsed,
                "error": stderr or stdout,
            }

        # Success
        self.storage.record_event(
            thread_id=thread_id,
            event_type="EXTERNAL_SEND_COMPLETED",
            message_id=request_id,
            payload={
                "connector": self.connector_id,
                "request_id": request_id,
                "conversation_id": req_conv_id,
                "elapsed_seconds": elapsed,
            },
        )
        return {
            "status": "EXTERNAL_SEND_COMPLETED",
            "request_id": request_id,
            "elapsed_seconds": elapsed,
            "stdout": stdout,
        }

    def reconcile_browser_response(
        self,
        thread_id: str,
        request_id: str,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Trusted read-only Browser response acquisition and reconciliation:
        1. Loads authoritative request identity and durable conversation binding.
        2. Checks if response already exists (idempotency).
        3. Invokes trusted read-only OpenCLI operation for exact conversation.
        4. Validates conversation provenance and strict Browser verdict (APPROVE | REVISE | BLOCKED).
        5. Emits authoritative RESPONSE_READY.
        """
        cmd_timeout = timeout or self.default_timeout

        # Check existing messages in thread for idempotency
        messages = self.storage.get_messages(thread_id)
        target_req = None
        for m in messages:
            if m["message_id"] == request_id:
                target_req = m
            if m.get("reply_to") == request_id and m.get("message_type") == "review.response":
                return {
                    "status": "CACHED_RESPONSE_READY",
                    "request_id": request_id,
                    "message": m,
                }

        if not target_req:
            raise ValueError(f"Request message '{request_id}' not found in thread '{thread_id}'")

        req_meta = target_req.get("metadata") or {}
        bound_conv_id = req_meta.get("conversation_id")
        if not bound_conv_id:
            raise ValueError(f"Request '{request_id}' has no durable conversation_id binding")

        artifact_id = target_req.get("artifact_id")

        # 3. Read from browser using OpenCLI read-only detail command
        read_cmd = [
            "opencli",
            "chatgpt",
            "detail",
            bound_conv_id,
            "-f",
            "json",
        ]

        returncode, stdout, stderr = self.opencli_runner(read_cmd, cmd_timeout)
        if returncode != 0:
            raise RuntimeError(f"OpenCLI read failed (code {returncode}): {stderr or stdout}")

        # Extract text and provenance from OpenCLI output
        raw_text = ""
        provenance_conv_id = ""
        try:
            parsed_out = json.loads(stdout.strip())
            if isinstance(parsed_out, list) and len(parsed_out) > 0:
                # OpenCLI detail returns list of messages or entries
                # Find last assistant text
                for entry in reversed(parsed_out):
                    if isinstance(entry, dict):
                        role = entry.get("Role") or entry.get("role") or ""
                        if role.lower() in ("assistant", "chatgpt") or not role:
                            raw_text = entry.get("Text") or entry.get("text") or entry.get("response") or ""
                            if raw_text:
                                break
                provenance_conv_id = bound_conv_id
            elif isinstance(parsed_out, dict):
                raw_text = parsed_out.get("response") or parsed_out.get("Text") or parsed_out.get("text") or stdout
                provenance_conv_id = parsed_out.get("conversationId") or bound_conv_id
            else:
                raw_text = stdout
                provenance_conv_id = bound_conv_id
        except Exception:
            raw_text = stdout
            provenance_conv_id = bound_conv_id

        # 4. Strictly parse verdict from trusted browser text
        parsed_verdict = parse_strict_browser_response(
            raw_text=raw_text,
            expected_request_id=request_id,
            expected_artifact_id=artifact_id,
        )

        decision = parsed_verdict["decision"]
        resp_msg_id = f"resp-{request_id}"
        resp_payload = {
            "decision": decision,
            "feedback": parsed_verdict["feedback"],
            "next_steps": parsed_verdict["next_steps"],
            "reviewed_artifact": artifact_id,
            "conversation_id": bound_conv_id,
        }

        msg, is_new, ev = self.storage.create_message(
            message_id=resp_msg_id,
            thread_id=thread_id,
            sender=self.connector_id,
            recipient="ide:agent",
            message_type="review.response",
            reply_to=request_id,
            artifact_id=artifact_id,
            content=raw_text,
            metadata=resp_payload,
            status="COMPLETED",
        )

        ready_ev = self.storage.record_event(
            thread_id=thread_id,
            event_type="RESPONSE_READY",
            message_id=resp_msg_id,
            payload={
                "response_id": resp_msg_id,
                "request_id": request_id,
                "artifact_id": artifact_id,
                "decision": decision,
                "conversation_id": bound_conv_id,
            },
        )
        return {
            "status": "RESPONSE_RECEIVED",
            "message": msg,
            "event": ready_ev,
            "verdict": parsed_verdict,
        }


def run_sse_connector_worker(
    hub_url: str,
    thread_id: str,
    conversation_id: str,
    storage: Storage,
    connector: OpenCLIBrowserConnector,
    stop_event: Optional[Any] = None,
    max_events: int = 1,
):
    """
    Subscribes to Hub SSE stream and event-drivenly triggers connector processing
    upon receiving REQUEST_CREATED. Never uses while-sleep database polling.
    """
    stream_url = f"{hub_url.rstrip('/')}/api/threads/{thread_id}/events/stream"
    req = urllib.request.Request(stream_url, headers={"Accept": "text/event-stream"})

    processed_count = 0
    with urllib.request.urlopen(req, timeout=15.0) as resp:
        while processed_count < max_events and (stop_event is None or not stop_event.is_set()):
            line = resp.readline().decode("utf-8")
            if not line:
                break
            line = line.strip()
            if line.startswith("data:"):
                raw_json = line[5:].strip()
                event = json.loads(raw_json)
                if event.get("event_type") == "REQUEST_CREATED":
                    req_id = event.get("message_id")
                    if req_id:
                        connector.process_review_request(
                            thread_id=thread_id,
                            request_id=req_id,
                            expected_conversation_id=conversation_id,
                        )
                        processed_count += 1
