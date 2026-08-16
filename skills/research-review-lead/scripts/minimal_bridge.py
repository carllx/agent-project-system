"""Minimal Browser Review Bridge.

Provides a clean, bounded, fast-returning, exactly-once bridge between the
IDE Agent and the Browser Review Lead via OpenCLI.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

DECISION_CHOICES = {"APPROVE", "REVISE", "BLOCKED"}
STATE_PREPARED = "PREPARED"
STATE_SEND_ATTEMPTED = "SEND_ATTEMPTED"
STATE_RESPONSE_RECEIVED = "RESPONSE_RECEIVED"

DEFAULT_COMMAND_TIMEOUT_SECONDS = 30

INERT_BOOTSTRAP_PROMPT = (
    "Initialize Browser Review Lead session. Awaiting formal Review Requests."
)


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def render_canonical_review_request(
    request_id: str,
    artifact_id: str,
    review_prompt: str,
) -> str:
    """Deterministic rendering of the canonical Browser Review Request envelope."""
    req = request_id.strip()
    art = artifact_id.strip()
    task = review_prompt.strip()
    return (
        "BROWSER_REVIEW_REQUEST\n\n"
        f"REQUEST_ID: {req}\n"
        f"ARTIFACT_ID: {art}\n\n"
        "REVIEW_TASK:\n"
        f"{task}\n\n"
        "REQUIRED_RESPONSE_FORMAT:\n"
        "Return exactly one JSON object:\n"
        "```json\n"
        "{\n"
        f'  "request_id": "{req}",\n'
        f'  "artifact_id": "{art}",\n'
        '  "decision": "APPROVE | REVISE | BLOCKED",\n'
        '  "feedback": "<non-empty string>",\n'
        '  "next_steps": ["..."]\n'
        "}\n"
        "```\n\n"
        "RULES:\n"
        "- Do not modify or omit request_id or artifact_id.\n"
        "- Do not emit APPROVE unless you have actually verified the review task.\n"
        "- If review cannot be completed or is unsafe, return decision: \"BLOCKED\".\n"
    )


def compute_request_hash(canonical_rendered_message: str) -> str:
    """Deterministic SHA256 of the exact canonical message rendered for external write."""
    return hashlib.sha256(canonical_rendered_message.encode("utf-8")).hexdigest()


@dataclass
class ReviewReceipt:
    request_id: str
    request_hash: str
    artifact_id: str
    conversation_id: str
    send_state: str
    created_at: str
    send_attempted_at: str | None = None
    response_received_at: str | None = None
    last_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReviewReceipt:
        return cls(
            request_id=data["request_id"],
            request_hash=data["request_hash"],
            artifact_id=data["artifact_id"],
            conversation_id=data["conversation_id"],
            send_state=data["send_state"],
            created_at=data["created_at"],
            send_attempted_at=data.get("send_attempted_at"),
            response_received_at=data.get("response_received_at"),
            last_error=data.get("last_error"),
        )


def _receipt_path(receipt_dir: Path, request_id: str) -> Path:
    safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", request_id)
    return receipt_dir / f"{safe_name}.receipt.json"


def load_receipt(receipt_dir: Path, request_id: str) -> ReviewReceipt | None:
    path = _receipt_path(receipt_dir, request_id)
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as stream:
        return ReviewReceipt.from_dict(json.load(stream))


def save_receipt_atomic(receipt_dir: Path, receipt: ReviewReceipt) -> None:
    receipt_dir.mkdir(parents=True, exist_ok=True)
    target = _receipt_path(receipt_dir, receipt.request_id)
    fd, tmp = tempfile.mkstemp(prefix=f".{target.name}.", dir=str(receipt_dir))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(receipt.to_dict(), stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(tmp, target)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def parse_strict_response(
    raw_text: str,
    expected_request_id: str,
    expected_artifact_id: str,
) -> dict[str, Any]:
    """Parse strict JSON review response block and verify required safety bindings."""
    if not isinstance(raw_text, str) or not raw_text.strip():
        raise ValueError("raw_text is empty or not a string")

    codeblock_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw_text, re.DOTALL)
    if codeblock_match:
        candidate_json = codeblock_match.group(1)
    else:
        candidate_match = re.search(r"(\{.*\})", raw_text, re.DOTALL)
        if candidate_match:
            candidate_json = candidate_match.group(1)
        else:
            raise ValueError("No JSON object found in response")

    try:
        parsed = json.loads(candidate_json)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Malformed JSON response: {exc}") from exc

    if not isinstance(parsed, dict):
        raise ValueError("Response JSON must be a single JSON object")

    req_id = parsed.get("request_id")
    if req_id != expected_request_id:
        raise ValueError(
            f"request_id mismatch: expected '{expected_request_id}', got '{req_id}'"
        )

    art_id = parsed.get("artifact_id")
    if art_id != expected_artifact_id:
        raise ValueError(
            f"artifact_id mismatch: expected '{expected_artifact_id}', got '{art_id}'"
        )

    decision = parsed.get("decision")
    if decision not in DECISION_CHOICES:
        raise ValueError(
            f"Invalid decision: '{decision}'. Must be one of {sorted(DECISION_CHOICES)}"
        )

    feedback = parsed.get("feedback")
    if not isinstance(feedback, str) or not feedback.strip():
        raise ValueError("feedback must be a non-empty string")

    next_steps = parsed.get("next_steps", [])
    if not isinstance(next_steps, list):
        raise ValueError("next_steps must be a list")

    return {
        "request_id": req_id,
        "artifact_id": art_id,
        "decision": decision,
        "feedback": feedback.strip(),
        "next_steps": [str(step) for step in next_steps],
    }


def _resolve_opencli_command() -> list[str]:
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


def execute_opencli_command(
    args: list[str],
    *,
    timeout_seconds: int = DEFAULT_COMMAND_TIMEOUT_SECONDS,
    runner: Callable[[list[str], int], tuple[int, str, str]] | None = None,
) -> tuple[int, str, str]:
    """Bounded subprocess execution for OpenCLI commands."""
    if runner is not None:
        return runner(args, timeout_seconds)

    base_cmd = _resolve_opencli_command()
    full_cmd = [*base_cmd, *args]

    try:
        completed = subprocess.run(
            full_cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            check=False,
        )
        return completed.returncode, completed.stdout, completed.stderr
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(
            f"OpenCLI command timed out after {timeout_seconds}s: {' '.join(full_cmd)}"
        ) from exc
    except OSError as exc:
        raise RuntimeError(
            f"Failed to execute OpenCLI ({full_cmd}): {exc}"
        ) from exc


def _parse_opencli_output(stdout: str) -> dict[str, Any]:
    text = stdout.strip()
    if not text:
        return {}
    try:
        data = json.loads(text)
        if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
            return data[0]
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    m_conv = re.search(r"(?:conversationId|Url|url|Id|id):\s*([^\r\n]+)", text)
    m_resp = re.search(r"(?:response|Text|text):\s*(?:\|-?\s*\n)?(.*)", text, re.DOTALL)
    if m_conv:
        conv_raw = m_conv.group(1).strip().strip("'\"")
        m_uuid = re.search(r"([0-9a-fA-F-]{36})", conv_raw)
        conv_id = m_uuid.group(1) if m_uuid else conv_raw
        resp_text = m_resp.group(1).strip() if m_resp else text
        return {"conversationId": conv_id, "response": resp_text}

    return {"raw_text": text}


def bootstrap_conversation(
    *,
    timeout_seconds: int = DEFAULT_COMMAND_TIMEOUT_SECONDS,
    opencli_runner: Callable[[list[str], int], tuple[int, str, str]] | None = None,
) -> dict[str, Any]:
    """Create a new inert Review conversation via OpenCLI --new using fixed constant prompt."""
    cmd_args = ["chatgpt", "ask", "--new", "-f", "json", "--timeout", str(timeout_seconds), INERT_BOOTSTRAP_PROMPT]

    code, stdout, stderr = execute_opencli_command(
        cmd_args,
        timeout_seconds=timeout_seconds,
        runner=opencli_runner,
    )

    if code != 0:
        raise RuntimeError(f"Bootstrap failed (exit {code}): {stderr.strip() or stdout.strip()}")

    try:
        entry = _parse_opencli_output(stdout)
    except ValueError as exc:
        raise RuntimeError(f"Failed to parse bootstrap output: {exc}") from exc

    conv_id = entry.get("conversationId")
    if not conv_id:
        raise RuntimeError("OpenCLI bootstrap did not return a valid conversationId")

    return {
        "status": "CONVERSATION_ESTABLISHED",
        "conversation_id": conv_id,
        "conversation_url": entry.get("conversationUrl"),
    }


def dispatch_review(
    *,
    request_id: str,
    artifact_id: str,
    review_prompt: str,
    receipt_dir: Path,
    conversation_id: str,
    timeout_seconds: int = DEFAULT_COMMAND_TIMEOUT_SECONDS,
    opencli_runner: Callable[[list[str], int], tuple[int, str, str]] | None = None,
) -> dict[str, Any]:
    """Execute formal review submission using native fast non-waiting write."""
    if not request_id or not request_id.strip():
        raise ValueError("request_id is required")
    if not artifact_id or not artifact_id.strip():
        raise ValueError("artifact_id is required")
    if not review_prompt or not review_prompt.strip():
        raise ValueError("review_prompt is required")
    if not conversation_id or not conversation_id.strip():
        raise ValueError("conversation_id is required for formal review. Establish conversation via bootstrap first.")

    target_conv = conversation_id.strip()
    canonical_message = render_canonical_review_request(request_id, artifact_id, review_prompt)
    request_hash = compute_request_hash(canonical_message)
    receipt = load_receipt(receipt_dir, request_id)

    if receipt is not None:
        if receipt.request_hash != request_hash:
            raise ValueError(
                f"Existing receipt for request_id '{request_id}' has different canonical request_hash"
            )
        if receipt.artifact_id != artifact_id.strip():
            raise ValueError(
                f"Existing receipt for request_id '{request_id}' has different artifact_id"
            )
        if receipt.conversation_id != target_conv:
            raise ValueError(
                f"Existing receipt for request_id '{request_id}' has different conversation_id"
            )

        if receipt.send_state == STATE_RESPONSE_RECEIVED:
            return {
                "status": "CACHED_RESPONSE_READY",
                "conversation_id": receipt.conversation_id,
                "receipt": receipt.to_dict(),
            }
        if receipt.send_state == STATE_SEND_ATTEMPTED:
            # Exactly-once rule: do NOT send again. Check read-only reconciliation.
            reconcile_res = reconcile_review(
                request_id=request_id.strip(),
                artifact_id=artifact_id.strip(),
                receipt_dir=receipt_dir,
                conversation_id=receipt.conversation_id,
                timeout_seconds=timeout_seconds,
                opencli_runner=opencli_runner,
            )
            return reconcile_res
    else:
        # Pre-seed PREPARED with durable conversation_id
        receipt = ReviewReceipt(
            request_id=request_id.strip(),
            request_hash=request_hash,
            artifact_id=artifact_id.strip(),
            conversation_id=target_conv,
            send_state=STATE_PREPARED,
            created_at=_utc_iso(),
        )
        save_receipt_atomic(receipt_dir, receipt)

    # Formal review submission uses native --wait false for fast non-waiting send
    cmd_args = [
        "chatgpt", "ask",
        "--conversation", target_conv,
        "--wait", "false",
        "-f", "json",
        "--timeout", str(timeout_seconds),
        canonical_message,
    ]

    # Mark durable send attempt with known conversation_id BEFORE external write
    receipt.send_state = STATE_SEND_ATTEMPTED
    receipt.send_attempted_at = _utc_iso()
    save_receipt_atomic(receipt_dir, receipt)

    code, stdout, stderr = execute_opencli_command(
        cmd_args,
        timeout_seconds=timeout_seconds,
        runner=opencli_runner,
    )

    if code != 0:
        receipt.last_error = f"OpenCLI exit code {code}: {stderr.strip()}"
        save_receipt_atomic(receipt_dir, receipt)
        raise RuntimeError(f"OpenCLI execution failed (exit {code}): {stderr.strip() or stdout.strip()}")

    entry = _parse_opencli_output(stdout)
    active_conv_id = entry.get("conversationId") or target_conv
    receipt.conversation_id = active_conv_id
    receipt.last_error = None
    save_receipt_atomic(receipt_dir, receipt)

    return {
        "status": "RESPONSE_PENDING",
        "request_id": request_id.strip(),
        "conversation_id": active_conv_id,
        "write_attempted": True,
        "receipt": receipt.to_dict(),
    }


def reconcile_review(
    *,
    request_id: str,
    artifact_id: str,
    receipt_dir: Path,
    conversation_id: str,
    timeout_seconds: int = DEFAULT_COMMAND_TIMEOUT_SECONDS,
    opencli_runner: Callable[[list[str], int], tuple[int, str, str]] | None = None,
) -> dict[str, Any]:
    """Strictly read-only reconciliation against existing conversation."""
    receipt = load_receipt(receipt_dir, request_id)
    if receipt is None:
        raise ValueError(f"No receipt found for request_id '{request_id}'")

    code, stdout, stderr = execute_opencli_command(
        ["chatgpt", "detail", conversation_id, "-f", "json"],
        timeout_seconds=timeout_seconds,
        runner=opencli_runner,
    )

    if code != 0:
        return {
            "status": "RECONCILE_FAILED",
            "error": f"OpenCLI detail failed (exit {code}): {stderr.strip()}",
            "receipt": receipt.to_dict(),
        }

    try:
        messages = json.loads(stdout)
    except json.JSONDecodeError:
        return {
            "status": "RECONCILE_FAILED",
            "error": "Failed to parse detail output as JSON",
            "receipt": receipt.to_dict(),
        }

    if not isinstance(messages, list):
        return {
            "status": "RECONCILE_FAILED",
            "error": "Detail JSON output must be a message list",
            "receipt": receipt.to_dict(),
        }

    # Inspect messages from newest to oldest for a valid matching response block
    for msg in reversed(messages):
        if not isinstance(msg, dict):
            continue
        role = msg.get("Role") or msg.get("role")
        if role and str(role).lower() != "assistant":
            continue
        text = msg.get("Text") or msg.get("text") or ""
        try:
            parsed = parse_strict_response(
                raw_text=text,
                expected_request_id=request_id,
                expected_artifact_id=artifact_id,
            )
            receipt.conversation_id = conversation_id
            receipt.send_state = STATE_RESPONSE_RECEIVED
            receipt.response_received_at = _utc_iso()
            receipt.last_error = None
            save_receipt_atomic(receipt_dir, receipt)
            return {
                "status": "RESPONSE_READY",
                "conversation_id": conversation_id,
                "response": parsed,
                "receipt": receipt.to_dict(),
            }
        except ValueError:
            continue

    return {
        "status": "RESPONSE_PENDING",
        "conversation_id": conversation_id,
        "receipt": receipt.to_dict(),
    }
