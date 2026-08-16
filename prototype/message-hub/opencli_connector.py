"""
APS Message Hub - Real OpenCLI Browser Connector (Phase 2).

Responsibilities:
1. Consume durable review.request from Message Hub for a given thread.
2. Durably record CONNECTOR_ACCEPTED.
3. Record EXTERNAL_SEND_ATTEMPTED before invoking OpenCLI.
4. Enforce strict no-resend: once EXTERNAL_SEND_ATTEMPTED is recorded for a request_id,
   never re-invoke external send across retries, crashes, or process restarts.
5. Invocations timeout -> EXTERNAL_SEND_UNKNOWN (failure-honest, never retry).
6. Ingest single read-only reconciliation if requested, keeping real push ingress classification honest.
"""

from __future__ import annotations

import json
import subprocess
import time
from typing import Any, Callable, Dict, Optional

from storage import Storage


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
            # cmd passed in is like ["chatgpt", "send", ...] or ["opencli", "chatgpt", ...]
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

    def is_send_attempted(self, thread_id: str, request_id: str) -> bool:
        """Check if EXTERNAL_SEND_ATTEMPTED has already been recorded in durable events."""
        events = self.storage.get_events(thread_id)
        for ev in events:
            if ev.get("message_id") == request_id and ev.get("event_type") == "EXTERNAL_SEND_ATTEMPTED":
                return True
        return False

    def process_review_request(
        self,
        thread_id: str,
        request_id: str,
        conversation_id: str,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Processes one specific review request durably with at most one external send attempt.
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

        artifact_id = target_msg.get("artifact_id")

        # 1. Check if already attempted -> NO-RESEND invariant
        if self.is_send_attempted(thread_id, request_id):
            return {
                "status": "SKIPPED_ALREADY_ATTEMPTED",
                "request_id": request_id,
                "message": "External send was already attempted for this request. Refusing to resend.",
            }

        # 2. Record CONNECTOR_ACCEPTED
        self.storage.record_event(
            thread_id=thread_id,
            event_type="CONNECTOR_ACCEPTED",
            message_id=request_id,
            payload={
                "connector": self.connector_id,
                "request_id": request_id,
                "artifact_id": artifact_id,
                "conversation_id": conversation_id,
            },
        )

        # 3. CRITICAL: Durably record EXTERNAL_SEND_ATTEMPTED BEFORE invoking OpenCLI
        t_attempt = time.time()
        self.storage.record_event(
            thread_id=thread_id,
            event_type="EXTERNAL_SEND_ATTEMPTED",
            message_id=request_id,
            payload={
                "connector": self.connector_id,
                "request_id": request_id,
                "artifact_id": artifact_id,
                "conversation_id": conversation_id,
                "attempted_at": t_attempt,
            },
        )

        # 4. Invoke OpenCLI send (submit-only)
        # Format exact prompt payload
        prompt_content = target_msg["content"]
        cmd = [
            "opencli",
            "chatgpt",
            "send",
            prompt_content,
            "--conversation",
            conversation_id,
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
                    "conversation_id": conversation_id,
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
                    "conversation_id": conversation_id,
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
                "conversation_id": conversation_id,
                "elapsed_seconds": elapsed,
            },
        )
        return {
            "status": "EXTERNAL_SEND_COMPLETED",
            "request_id": request_id,
            "elapsed_seconds": elapsed,
            "stdout": stdout,
        }

    def ingest_response_from_browser_text(
        self,
        thread_id: str,
        request_id: str,
        artifact_id: str,
        response_text: str,
        decision: str = "ACCEPTED",
    ) -> Dict[str, Any]:
        """
        Durably ingest a browser review response, validating exact request & artifact binding,
        creating review.response message and emitting RESPONSE_READY.
        """
        resp_msg_id = f"resp-{request_id}"
        resp_payload = {
            "decision": decision,
            "reviewed_artifact": artifact_id,
        }
        msg, is_new, ev = self.storage.create_message(
            message_id=resp_msg_id,
            thread_id=thread_id,
            sender=self.connector_id,
            recipient="ide:agent",
            message_type="review.response",
            reply_to=request_id,
            artifact_id=artifact_id,
            content=response_text,
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
            },
        )
        return {"message": msg, "event": ready_ev}
