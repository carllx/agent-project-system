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
            request_id=data["request_id"].strip(),
            request_hash=data["request_hash"].strip(),
            artifact_id=data["artifact_id"].strip(),
            conversation_id=data["conversation_id"].strip(),
            send_state=data["send_state"],
            created_at=data["created_at"],
            send_attempted_at=data.get("send_attempted_at"),
            response_received_at=data.get("response_received_at"),
            last_error=data.get("last_error"),
        )


def get_canonical_receipt_dir() -> Path:
    """Return the absolute per-user canonical directory for storing review receipts."""
    return Path.home() / ".agent-project-system" / "browser-review-receipts"


def _receipt_path(receipt_dir: Path, request_id: str) -> Path:
    normalized = request_id.strip()
    safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", normalized)
    return receipt_dir / f"{safe_name}.receipt.json"


def load_receipt(receipt_dir: Path | None, request_id: str) -> ReviewReceipt | None:
    if not isinstance(request_id, str):
        return None
    store_dir = receipt_dir if receipt_dir is not None else get_canonical_receipt_dir()
    path = _receipt_path(store_dir, request_id)
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as stream:
        return ReviewReceipt.from_dict(json.load(stream))


def save_receipt_atomic(receipt_dir: Path | None, receipt: ReviewReceipt) -> None:
    store_dir = receipt_dir if receipt_dir is not None else get_canonical_receipt_dir()
    store_dir.mkdir(parents=True, exist_ok=True)
    target = _receipt_path(store_dir, receipt.request_id)
    fd, tmp = tempfile.mkstemp(prefix=f".{target.name}.", dir=str(store_dir))
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

    exp_req = expected_request_id.strip()
    exp_art = expected_artifact_id.strip()
    text = raw_text.strip()

    # Find all fenced JSON blocks
    fenced_blocks = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)

    # Check for bare JSON objects outside fenced blocks
    text_without_fences = re.sub(r"```(?:json)?\s*\{.*?\}\s*```", "", text, flags=re.DOTALL)
    bare_objects_outside_fences = re.findall(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text_without_fences, re.DOTALL)

    if len(fenced_blocks) == 1:
        if len(bare_objects_outside_fences) > 0:
            raise ValueError("Ambiguous response: found fenced JSON block and additional bare JSON object outside fence")
        candidate_json = fenced_blocks[0]
    elif len(fenced_blocks) > 1:
        raise ValueError(f"Ambiguous response: found {len(fenced_blocks)} fenced JSON blocks")
    else:
        # 0 fenced blocks: check bare objects
        if len(bare_objects_outside_fences) == 1:
            candidate_json = bare_objects_outside_fences[0]
        elif len(bare_objects_outside_fences) > 1:
            raise ValueError(f"Ambiguous response: found {len(bare_objects_outside_fences)} bare JSON objects")
        else:
            raise ValueError("No JSON object found in response")

    try:
        parsed = json.loads(candidate_json)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Malformed JSON response: {exc}") from exc

    if not isinstance(parsed, dict):
        raise ValueError("Response JSON must be a single JSON object")

    req_id = parsed.get("request_id")
    if not isinstance(req_id, str) or req_id != exp_req:
        raise ValueError(
            f"request_id mismatch: expected exact '{exp_req}', got '{req_id}'"
        )

    art_id = parsed.get("artifact_id")
    if not isinstance(art_id, str) or art_id != exp_art:
        raise ValueError(
            f"artifact_id mismatch: expected exact '{exp_art}', got '{art_id}'"
        )

    decision = parsed.get("decision")
    if decision not in DECISION_CHOICES:
        raise ValueError(
            f"Invalid decision: '{decision}'. Must be one of {sorted(DECISION_CHOICES)}"
        )

    feedback = parsed.get("feedback")
    if not isinstance(feedback, str) or not feedback.strip():
        raise ValueError("feedback must be a non-empty string")

    next_steps = parsed.get("next_steps")
    if next_steps is None:
        next_steps = []
    if not isinstance(next_steps, list):
        raise ValueError("next_steps must be a list of strings")
    for idx, step in enumerate(next_steps):
        if not isinstance(step, str):
            raise ValueError(f"next_steps[{idx}] must be a string, got {type(step).__name__}")

    return {
        "request_id": exp_req,
        "artifact_id": exp_art,
        "decision": decision,
        "feedback": feedback.strip(),
        "next_steps": [s.strip() for s in next_steps],
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
        "conversation_id": conv_id.strip(),
        "conversation_url": entry.get("conversationUrl"),
    }


def dispatch_review(
    *,
    request_id: str,
    artifact_id: str,
    review_prompt: str,
    receipt_dir: Path | None = None,
    conversation_id: str,
    timeout_seconds: int = DEFAULT_COMMAND_TIMEOUT_SECONDS,
    opencli_runner: Callable[[list[str], int], tuple[int, str, str]] | None = None,
) -> dict[str, Any]:
    """Execute formal review submission using native fast non-waiting write."""
    if not isinstance(request_id, str) or not request_id.strip():
        raise ValueError("request_id is required")
    if not isinstance(artifact_id, str) or not artifact_id.strip():
        raise ValueError("artifact_id is required")
    if not isinstance(review_prompt, str) or not review_prompt.strip():
        raise ValueError("review_prompt is required")
    if not isinstance(conversation_id, str) or not conversation_id.strip():
        raise ValueError("conversation_id is required for formal review. Establish conversation via bootstrap first.")

    norm_req = request_id.strip()
    norm_art = artifact_id.strip()
    norm_prompt = review_prompt.strip()
    target_conv = conversation_id.strip()

    canonical_message = render_canonical_review_request(norm_req, norm_art, norm_prompt)
    request_hash = compute_request_hash(canonical_message)
    receipt = load_receipt(receipt_dir, norm_req)

    if receipt is not None:
        if receipt.request_hash != request_hash:
            raise ValueError(
                f"Existing receipt for request_id '{norm_req}' has different canonical request_hash"
            )
        if receipt.artifact_id != norm_art:
            raise ValueError(
                f"Existing receipt for request_id '{norm_req}' has different artifact_id"
            )
        if receipt.conversation_id != target_conv:
            raise ValueError(
                f"Existing receipt for request_id '{norm_req}' has different conversation_id"
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
                request_id=norm_req,
                artifact_id=norm_art,
                receipt_dir=receipt_dir,
                conversation_id=receipt.conversation_id,
                timeout_seconds=timeout_seconds,
                opencli_runner=opencli_runner,
            )
            return reconcile_res
    else:
        # Pre-seed PREPARED with durable conversation_id
        receipt = ReviewReceipt(
            request_id=norm_req,
            request_hash=request_hash,
            artifact_id=norm_art,
            conversation_id=target_conv,
            send_state=STATE_PREPARED,
            created_at=_utc_iso(),
        )
        save_receipt_atomic(receipt_dir, receipt)

    # Formal review submission uses native submit-only chatgpt send
    cmd_args = [
        "chatgpt", "send",
        canonical_message,
        "--conversation", target_conv,
        "-f", "json",
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

    try:
        entry = _parse_opencli_output(stdout)
        returned_conv_id = entry.get("conversationId")
        if returned_conv_id:
            returned_conv_id = returned_conv_id.strip()
            if returned_conv_id != target_conv:
                # Exact Conversation Must Never Drift: fail closed and preserve target_conv
                err_msg = (
                    f"Exact-target mismatch: OpenCLI returned foreign conversationId '{returned_conv_id}', "
                    f"expected '{target_conv}'"
                )
                receipt.last_error = err_msg
                save_receipt_atomic(receipt_dir, receipt)
                raise RuntimeError(err_msg)
    except ValueError:
        pass

    receipt.last_error = None
    save_receipt_atomic(receipt_dir, receipt)

    return {
        "status": "RESPONSE_PENDING",
        "request_id": norm_req,
        "conversation_id": target_conv,
        "write_attempted": True,
        "receipt": receipt.to_dict(),
    }


def reconcile_review(
    *,
    request_id: str,
    artifact_id: str,
    receipt_dir: Path | None = None,
    conversation_id: str | None = None,
    timeout_seconds: int = DEFAULT_COMMAND_TIMEOUT_SECONDS,
    opencli_runner: Callable[[list[str], int], tuple[int, str, str]] | None = None,
) -> dict[str, Any]:
    """Strictly read-only reconciliation using durable receipt identity."""
    if not isinstance(request_id, str) or not request_id.strip():
        raise ValueError("request_id is required for reconcile")
    if not isinstance(artifact_id, str) or not artifact_id.strip():
        raise ValueError("artifact_id is required for reconcile")

    norm_req = request_id.strip()
    norm_art = artifact_id.strip()
    norm_conv = conversation_id.strip() if conversation_id else None

    receipt = load_receipt(receipt_dir, norm_req)
    if receipt is None:
        raise ValueError(f"No receipt found for request_id '{norm_req}'")

    if receipt.request_id != norm_req:
        raise ValueError(f"Receipt request_id mismatch: stored '{receipt.request_id}', query '{norm_req}'")
    if receipt.artifact_id != norm_art:
        raise ValueError(f"Reconcile artifact_id mismatch: receipt has '{receipt.artifact_id}', query has '{norm_art}'")
    if norm_conv and receipt.conversation_id != norm_conv:
        raise ValueError(f"Reconcile conversation_id mismatch: receipt has '{receipt.conversation_id}', query has '{norm_conv}'")

    target_conv = receipt.conversation_id

    code, stdout, stderr = execute_opencli_command(
        ["chatgpt", "detail", target_conv, "-f", "json"],
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
                expected_request_id=norm_req,
                expected_artifact_id=norm_art,
            )
            receipt.conversation_id = target_conv
            receipt.send_state = STATE_RESPONSE_RECEIVED
            receipt.response_received_at = _utc_iso()
            receipt.last_error = None
            save_receipt_atomic(receipt_dir, receipt)
            return {
                "status": "RESPONSE_READY",
                "conversation_id": target_conv,
                "response": parsed,
                "receipt": receipt.to_dict(),
            }
        except ValueError:
            continue

    return {
        "status": "RESPONSE_PENDING",
        "conversation_id": target_conv,
        "receipt": receipt.to_dict(),
    }
