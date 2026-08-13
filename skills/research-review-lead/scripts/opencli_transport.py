#!/usr/bin/env python3
"""Bounded OpenCLI transport for the RR Lead loop.

New-conversation delivery is deliberately split into create, verify, and send.
The wrapper never sends a MESSAGE_ID more than once and never treats a message
found in a pre-existing conversation as a successful RR Lead delivery.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, NamedTuple
from urllib.parse import urlparse


PROCESS_MONOTONIC_STARTED = time.monotonic()
PROCESS_STARTED_AT = datetime.now(timezone.utc).isoformat(timespec="seconds")
COMMAND_WAIT_SECONDS = 15
ASK_HARD_TIMEOUT_GRACE_SECONDS = 1
POLL_INTERVAL_SECONDS = 5
TOTAL_RESPONSE_WAIT_SECONDS = 30
MAX_SEND_ATTEMPTS_PER_MESSAGE = 1
MAX_RECOVERY_ATTEMPTS = 1
MAX_DETAIL_CHECKS = 1
MAX_EXTERNAL_COMMANDS = 9
MAX_EXPERIMENT_SECONDS = 60
MAX_POST_SEND_NAVIGATION_WAIT_SECONDS = 30
MAX_NAVIGATION_STATUS_CHECKS = 10
MIN_NAVIGATION_STATUS_COMMAND_BUDGET_SECONDS = 3
POST_SEND_NAVIGATION_POLL_INTERVAL_SECONDS = 1
MAX_PENDING_RESPONSE_CONTINUATIONS = 3
PREPARE_MAX_SEND_ATTEMPTS = 0
PREPARE_MAX_RECOVERY_ATTEMPTS = 0
PREPARE_MAX_DETAIL_CHECKS = 0
PREPARE_MAX_EXTERNAL_COMMANDS = 4
RECENT_CANDIDATE_LIMIT = 3
STABLE_SECONDS = 3
DELIVERY_STATES = {
    "NOT_SENT",
    "CREATING_CONVERSATION",
    "VERIFYING_CONVERSATION",
    "SENDING",
    "SENT",
    "DELIVERY_UNKNOWN",
    "MISROUTED_DELIVERY",
    "DELIVERED",
    "RESPONSE_PENDING",
    "RESPONSE_READY",
    "RESPONSE_IDENTITY_MISSING",
    "RESPONSE_IDENTITY_MISMATCH",
    "RESPONSE_IDENTITY_AMBIGUOUS",
    "OUTBOUND_MESSAGE_IDENTITY_AMBIGUOUS",
    "RESPONSE_SOURCE_CONVERSATION_MISMATCH",
    "RESPONSE_IDENTITY_REJECTED",
    "RESPONSE_PROTOCOL_REJECTED",
    "BLOCKED_RESPONSE_TIMEOUT",
    "MANUAL_RELAY_REQUIRED",
    "FAILED",
}
NO_RESEND_STATES = DELIVERY_STATES - {"NOT_SENT"}

RR_RESPONSE_FIELDS = (
    "WORK_ITEM_ID",
    "IN_REPLY_TO_MESSAGE_ID",
    "ROUND",
    "REVIEW_DECISION",
    "WORK_ITEM_STATE",
    "ACCEPTANCE_STATUS",
    "FINDINGS",
    "BLOCKERS",
    "DEBT",
    "NEXT_WORK_ORDER",
    "VALIDATION",
    "USER_DECISION_REQUIRED",
)
RR_REPLY_ID_ALIAS = "REPLY_TO_MESSAGE_ID"
RR_OPTIONAL_RESPONSE_FIELDS = ("MESSAGE_ID", "MESSAGE_TYPE")
RR_ALLOWED_RESPONSE_FIELDS = (*RR_RESPONSE_FIELDS, RR_REPLY_ID_ALIAS, *RR_OPTIONAL_RESPONSE_FIELDS)
RR_REVIEW_BEGIN = "RR_REVIEW_BEGIN"
RR_REVIEW_END = "RR_REVIEW_END"
BOOTSTRAP_BEGIN_INIT = "BEGIN_RR_LEAD_INITIALIZATION"
BOOTSTRAP_END_INIT = "END_RR_LEAD_INITIALIZATION"
BOOTSTRAP_BEGIN_CONTEXT = "BEGIN_CONTEXT_PACKET"
BOOTSTRAP_END_CONTEXT = "END_CONTEXT_PACKET"


class ResponseMessageBatch(NamedTuple):
    """Messages and their transport-proven source as one immutable value."""

    conversation_id: str
    messages: tuple[dict[str, Any], ...]
    source_kind: str
    raw_output_path: str | None


def _load_experiment_protocol_module() -> Any:
    """Load the package-local protocol module without relying on cwd or package imports."""
    module_path = Path(__file__).resolve().with_name("experiment_protocol.py")
    spec = importlib.util.spec_from_file_location(
        "_rr_lead_experiment_protocol", module_path
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load experiment protocol module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    previous_dont_write_bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous_dont_write_bytecode
    return module


_EXPERIMENT_PROTOCOL = _load_experiment_protocol_module()
MAX_IDLE_WAIT_SECONDS = _EXPERIMENT_PROTOCOL.MAX_IDLE_WAIT_SECONDS
MAX_SCHEDULE_CALLS = _EXPERIMENT_PROTOCOL.MAX_SCHEDULE_CALLS
MAX_POLL_ATTEMPTS = _EXPERIMENT_PROTOCOL.MAX_POLL_ATTEMPTS
MAX_BACKGROUND_RESULT_CHECKS = _EXPERIMENT_PROTOCOL.MAX_BACKGROUND_RESULT_CHECKS
MAX_BACKGROUND_WAIT_SECONDS = _EXPERIMENT_PROTOCOL.MAX_BACKGROUND_WAIT_SECONDS
EXPERIMENT_ACTION_TYPES = _EXPERIMENT_PROTOCOL.EXPERIMENT_ACTION_TYPES
ASYNC_INCOMPLETE_STATES = _EXPERIMENT_PROTOCOL.ASYNC_INCOMPLETE_STATES
STANDING_WAIT_PATTERNS = _EXPERIMENT_PROTOCOL.STANDING_WAIT_PATTERNS
unresolved_required_values = _EXPERIMENT_PROTOCOL.unresolved_required_values
assess_experiment_protocol = _EXPERIMENT_PROTOCOL.assess_experiment_protocol
validate_experiment_report = _EXPERIMENT_PROTOCOL.validate_experiment_report


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-._")
    if not cleaned:
        raise ValueError("identifier contains no safe filename characters")
    return cleaned[:120]


def default_state_path(work_item_id: str, message_id: str) -> Path:
    return Path(tempfile.gettempdir()) / "research-review-lead" / safe_name(work_item_id) / f"{safe_name(message_id)}.json"


def write_receipt_path(work_item_id: str, message_id: str) -> Path:
    root = Path(
        os.environ.get("OPENCLI_TRANSPORT_RECEIPT_DIR")
        or (Path(tempfile.gettempdir()) / "research-review-lead" / "write-receipts")
    )
    return root / safe_name(work_item_id) / f"{safe_name(message_id)}.json"


def create_write_receipt(
    path: Path, work_item_id: str, message_id: str, state_path: Path,
) -> None:
    """Atomically claim the sole Product write for a logical Message ID."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({
        "work_item_id": work_item_id,
        "message_id": message_id,
        "state_file": str(state_path),
        "write_claimed_at": utc_now(),
    }, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    except FileExistsError as error:
        raise ValueError("MESSAGE_ID already has a canonical write receipt; same-ID resend is forbidden") from error
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=path.name, suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def save_raw(state: dict[str, Any], state_path: Path, label: str, result: dict[str, Any]) -> str:
    raw_dir = state_path.parent / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    sequence = len(state.setdefault("raw_outputs", [])) + 1
    path = raw_dir / f"{sequence:02d}-{safe_name(label)}.json"
    write_json(path, result)
    state["raw_outputs"].append(str(path))
    return str(path)


def direct_node_opencli_from_npm_shim(
    shim_path: Path, node_executable: str | None = None,
) -> list[str] | None:
    """Resolve an npm OpenCLI shim to Node + its package-declared bin entry."""
    try:
        shim_text = shim_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    match = re.search(
        r"node_modules[\\/](?P<package>(?:@[^\\/\s\"']+[\\/])?[^\\/\s\"']+)"
        r"[\\/](?P<entry>[^\"'\r\n]*?\.js)",
        shim_text,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    package_parts = match.group("package").replace("\\", "/").split("/")
    package_root = shim_path.parent.joinpath("node_modules", *package_parts)
    package_json_path = package_root / "package.json"
    try:
        package_data = json.loads(package_json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    declared_name = str(package_data.get("name") or "")
    if declared_name != "/".join(package_parts):
        return None
    declared_bin = package_data.get("bin")
    if isinstance(declared_bin, dict):
        declared_entry = declared_bin.get("opencli")
    elif isinstance(declared_bin, str):
        declared_entry = declared_bin
    else:
        declared_entry = None
    if not isinstance(declared_entry, str) or not declared_entry.strip():
        return None
    entry_path = (package_root / declared_entry).resolve()
    shim_entry_path = (
        package_root / Path(match.group("entry").replace("\\", "/"))
    ).resolve()
    try:
        entry_path.relative_to(package_root.resolve())
    except ValueError:
        return None
    if entry_path != shim_entry_path or not entry_path.is_file():
        return None
    if node_executable is None:
        bundled_node = shim_path.parent / "node.exe"
        node_executable = (
            str(bundled_node)
            if bundled_node.is_file()
            else shutil.which("node.exe") or shutil.which("node")
        )
    if not node_executable:
        return None
    return [node_executable, str(entry_path)]


def find_opencli() -> list[str]:
    test_executable = os.environ.get("OPENCLI_TRANSPORT_EXECUTABLE")
    if test_executable:
        return [sys.executable, test_executable]
    if os.name == "nt":
        for candidate in ("opencli.cmd", "opencli.ps1"):
            found = shutil.which(candidate)
            if found:
                direct_node = direct_node_opencli_from_npm_shim(Path(found))
                if direct_node:
                    return direct_node
    for candidate in ("opencli.cmd", "opencli.exe", "opencli"):
        found = shutil.which(candidate)
        if found:
            return ["powershell", "-NoProfile", "-File", found] if found.lower().endswith(".ps1") else [found]
    raise RuntimeError("opencli was not found on PATH")


def terminate_process_tree(process: subprocess.Popen[str]) -> bool:
    """Terminate one OpenCLI process tree after a bounded command timeout."""
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                timeout=5,
                check=False,
            )
        else:
            os.killpg(process.pid, 15)
        process.communicate(timeout=5)
    except (OSError, subprocess.SubprocessError):
        process.kill()
        try:
            process.communicate(timeout=5)
        except subprocess.SubprocessError:
            return False
    return process.poll() is not None


def run_opencli(args: list[str], timeout: float) -> dict[str, Any]:
    started = utc_now()
    popen_options: dict[str, Any] = {}
    if os.name == "nt":
        popen_options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_options["start_new_session"] = True
    process = subprocess.Popen(
        [*find_opencli(), *args], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace", **popen_options,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
        return {"started_at": started, "finished_at": utc_now(), "timed_out": False,
                "returncode": process.returncode, "stdout": stdout, "stderr": stderr,
                "process_tree_terminated": False}
    except subprocess.TimeoutExpired as error:
        terminated = terminate_process_tree(process)
        return {"started_at": started, "finished_at": utc_now(), "timed_out": True,
                "returncode": None, "stdout": _decode(error.stdout), "stderr": _decode(error.stderr),
                "process_tree_terminated": terminated}


def _decode(value: bytes | str | None) -> str:
    if value is None:
        return ""
    return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value


def parse_json(text: str) -> Any:
    stripped = text.strip()
    if not stripped:
        return None
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        starts = [i for token in ("[", "{") if (i := stripped.find(token)) >= 0]
        if not starts:
            return None
        try:
            return json.loads(stripped[min(starts):])
        except json.JSONDecodeError:
            return None


def cli_error_code(stderr: str) -> str | None:
    """Extract an exact code from OpenCLI's top-level YAML-like error envelope."""
    match = re.search(
        r"(?m)^error:\s*\r?\n(?:(?:[ \t]+[^\r\n]*\r?\n)*)^[ \t]+code:\s*([A-Z0-9_]+)\s*$",
        stderr,
    )
    return match.group(1) if match else None


def contains_chat_message(value: Any) -> bool:
    if isinstance(value, list):
        return any(contains_chat_message(item) for item in value)
    if not isinstance(value, dict):
        return False
    lowered = {str(key).lower(): item for key, item in value.items()}
    if "role" in lowered and any(key in lowered for key in ("text", "content", "message")):
        return True
    return any(
        contains_chat_message(lowered[key])
        for key in ("messages", "data", "result")
        if key in lowered
    )


def classify_chatgpt_read_result(result: dict[str, Any]) -> str:
    """Return EMPTY, NON_EMPTY, or UNPARSEABLE without guessing at UI data."""
    if result["timed_out"]:
        return "UNPARSEABLE"
    stdout = str(result.get("stdout") or "")
    stripped = stdout.strip()
    parsed = parse_json(stdout)
    if stripped:
        if stripped == "EMPTY_RESULT" and result["returncode"] == 0:
            return "EMPTY"
        if parsed in ([], {}):
            return "EMPTY" if result["returncode"] == 0 else "UNPARSEABLE"
        if parsed is None:
            return "UNPARSEABLE"
        if contains_chat_message(parsed):
            return "NON_EMPTY"
        return "UNPARSEABLE"
    if cli_error_code(str(result.get("stderr") or "")) == "EMPTY_RESULT":
        return "EMPTY"
    return "UNPARSEABLE"


def rows(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [row for row in value if isinstance(row, dict)]
    return [value] if isinstance(value, dict) else []


def pick(row: dict[str, Any], *names: str) -> Any:
    lowered = {str(key).lower(): value for key, value in row.items()}
    for name in names:
        if name.lower() in lowered:
            return lowered[name.lower()]
    return None


def conversation_identity(row: dict[str, Any]) -> tuple[str | None, str | None]:
    identity = pick(row, "Id", "conversationId", "ConversationId")
    url = pick(row, "Url", "conversationUrl", "ConversationUrl")
    return (str(identity) if identity else conversation_id_from_url(str(url or "")), str(url) if url else None)


def conversation_id_from_url(url: str) -> str | None:
    match = re.search(r"(?:https?://[^/]+)?/c/([A-Za-z0-9-]+)", url)
    return match.group(1) if match else None


def existing_chatgpt_conversation_id(url: str | None) -> str | None:
    """Return the ID only for an exact ChatGPT /c/<id> page."""
    if not url:
        return None
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return None
    if parsed.hostname not in {"chatgpt.com", "www.chatgpt.com"}:
        return None
    match = re.fullmatch(r"/c/([A-Za-z0-9-]+)", parsed.path)
    return match.group(1) if match else None


def set_state(state: dict[str, Any], delivery_state: str, note: str) -> None:
    if delivery_state not in DELIVERY_STATES:
        raise ValueError(f"invalid delivery state: {delivery_state}")
    state["delivery_state"] = delivery_state
    state["updated_at"] = utc_now()
    state.setdefault("transitions", []).append({"at": state["updated_at"], "state": delivery_state, "note": note})


def stop(state: dict[str, Any], reason: str, work_item_state: str = "BLOCKED") -> None:
    state["work_item_state"] = work_item_state
    state["stopped_at"] = utc_now()
    state["stop_reason"] = reason


def begin_operation(state: dict[str, Any], operation: str) -> None:
    """Start one bounded operation without rewriting the original send audit time."""
    started = utc_now()
    state.setdefault("original_send_started_at", state.get("started_at") or started)
    state["current_operation"] = operation
    state["current_operation_started_at"] = started
    state["current_operation_external_command_count"] = 0
    state["stopped_at"] = None
    state["stop_reason"] = None
    state["work_item_state"] = "IN_PROGRESS"
    if operation == "MANUAL_RECOVER":
        state["manual_recover_started_at"] = started
    elif operation == "PENDING_RESPONSE_CONTINUATION":
        state["pending_response_last_checked_at"] = started


def begin_post_send_verification(state: dict[str, Any]) -> None:
    """Start the bounded post-write observation operation after one write returned."""
    if not state.get("send_attempted") or state.get("send_attempt_count") != 1:
        raise RuntimeError(
            "POST_SEND_VERIFICATION requires exactly one recorded send attempt"
        )
    boundary = {
        "trigger": "WRITE_INVOCATION_RETURNED_CONTROL",
        "previous_operation": state.get("current_operation"),
        "previous_operation_started_at": state.get("current_operation_started_at"),
        "previous_operation_external_command_count": state.get(
            "current_operation_external_command_count", 0
        ),
        "previous_operation_elapsed_seconds": round(
            operation_elapsed_seconds(state), 3
        ),
    }
    begin_operation(state, "POST_SEND_VERIFICATION")
    state["operation_budget_excluded_navigation_seconds"] = 0.0
    boundary["started_at"] = state["current_operation_started_at"]
    state["post_send_verification_boundary"] = boundary


def operation_elapsed_seconds(state: dict[str, Any]) -> float:
    started_at = state.get("current_operation_started_at") or state["started_at"]
    started = datetime.fromisoformat(started_at)
    physical_elapsed = (datetime.now(timezone.utc) - started).total_seconds()
    navigation_excluded = float(
        state.get("operation_budget_excluded_navigation_seconds", 0.0)
    )
    return max(0.0, physical_elapsed - navigation_excluded)


def command(
    state: dict[str, Any],
    state_path: Path,
    label: str,
    args: list[str],
    timeout: int,
    before_invoke: Callable[[], None] | None = None,
) -> dict[str, Any] | None:
    operation_count = state.get(
        "current_operation_external_command_count", state["external_command_count"]
    )
    if operation_count >= state["parameters"]["max_external_commands"]:
        stop(state, "EXPERIMENT_BUDGET_EXHAUSTED: MAX_EXTERNAL_COMMANDS")
        return None
    elapsed = operation_elapsed_seconds(state)
    if elapsed >= state["parameters"]["max_experiment_seconds"]:
        stop(state, "EXPERIMENT_BUDGET_EXHAUSTED: MAX_EXPERIMENT_SECONDS")
        return None
    if before_invoke:
        before_invoke()
    state["external_command_count"] += 1
    state["current_operation_external_command_count"] = operation_count + 1
    if state.get("current_operation") == "MANUAL_RECOVER":
        state["manual_recover_external_command_count"] = operation_count + 1
    result = run_opencli(args, min(timeout, max(1, int(state["parameters"]["max_experiment_seconds"] - elapsed))))
    save_raw(state, state_path, label, result)
    return result


def remaining_experiment_seconds(state: dict[str, Any]) -> float:
    elapsed = operation_elapsed_seconds(state)
    return max(0.0, state["parameters"]["max_experiment_seconds"] - elapsed)


def result_rows(result: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not result or result["timed_out"] or result["returncode"] != 0:
        return []
    return rows(parse_json(result["stdout"]))


def yaml_scalar(value: str) -> str | None:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        quote = value[0]
        value = value[1:-1]
        if quote == "'":
            value = value.replace("''", "'")
    return value or None


def flat_ask_yaml_record(text: str) -> dict[str, str]:
    """Parse only the first strict flat ask record; never search response body lines."""
    lines = text.splitlines()
    first = next((index for index, line in enumerate(lines) if line.strip()), None)
    if first is None:
        return {}
    match = re.fullmatch(r"- conversationId:\s*(.*?)\s*", lines[first])
    if not match:
        return {}
    record: dict[str, str] = {}
    identity = yaml_scalar(match.group(1))
    if identity:
        record["conversationId"] = identity
    for line in lines[first + 1:]:
        if not line.strip():
            continue
        field = re.fullmatch(r"  (conversationUrl|tool|response):\s*(.*?)\s*", line)
        if not field:
            break
        name, raw_value = field.groups()
        value = yaml_scalar(raw_value)
        if value:
            record[name] = value
        if name == "response":
            break
    return record


def validated_ask_identity(
    identity: str | None, url: str | None
) -> tuple[str | None, str | None]:
    if identity and not re.fullmatch(r"[A-Za-z0-9-]+", identity):
        return None, None
    if url:
        url_identity = existing_chatgpt_conversation_id(url)
        if not url_identity or (identity and identity != url_identity):
            return None, None
        identity = identity or url_identity
    return (identity, url) if identity else (None, None)


def ask_identity(result: dict[str, Any]) -> tuple[str | None, str | None]:
    """Extract ask identity from JSON or the YAML emitted by real OpenCLI 1.8.6."""
    for row in result_rows(result):
        identity, url = conversation_identity(row)
        if identity or url:
            return validated_ask_identity(identity, url)
    record = flat_ask_yaml_record(str(result.get("stdout") or ""))
    return validated_ask_identity(
        record.get("conversationId"), record.get("conversationUrl")
    )


def ask_response(result: dict[str, Any]) -> str | None:
    for row in result_rows(result):
        response = pick(row, "response")
        if response:
            return str(response)
    response = flat_ask_yaml_record(str(result.get("stdout") or "")).get("response")
    return None if response in {"|", "|-", "|+", ">", ">-", ">+"} else response


def classify_ask_delivery(result: dict[str, Any], identity: str | None) -> str:
    if result.get("timed_out"):
        return "C. ASK_TIMEOUT_OR_TRANSPORT_ERROR"
    if result.get("returncode") == 0 and identity:
        return "A. ASK_CONFIRMED_DELIVERY_WITH_ID"
    if result.get("returncode") == 0:
        return "B. ASK_COMPLETED_WITHOUT_ID"
    if cli_error_code(str(result.get("stderr") or "")) in {
        "INVALID_ARGUMENT", "REQUIRED_VALUE_UNRESOLVED", "UNAUTHORIZED",
    }:
        return "D. ASK_REJECTED_BEFORE_DELIVERY"
    return "C. ASK_TIMEOUT_OR_TRANSPORT_ERROR"


def page_mode(url: str | None) -> str:
    if existing_chatgpt_conversation_id(url):
        return "CONVERSATION"
    if not url:
        return "UNKNOWN"
    parsed = urlparse(url)
    if parsed.hostname not in {"chatgpt.com", "www.chatgpt.com"}:
        return "UNKNOWN"
    if parsed.path == "/new":
        return "NEW"
    if parsed.path in {"", "/"}:
        return "ROOT"
    return "UNKNOWN"


def status_url(result: dict[str, Any] | None) -> str | None:
    for row in result_rows(result):
        url = pick(row, "Url")
        if url:
            return str(url)
    return None


def observe_candidate(
    state: dict[str, Any], identity: str | None, source: str
) -> None:
    """Preserve the first non-empty Conversation candidate and record conflicts."""
    if not identity:
        return
    current = state.get("candidate_conversation_id")
    if not current:
        state["candidate_conversation_id"] = identity
        state["candidate_conversation_source"] = source
        return
    if current == identity:
        return
    conflict = {
        "preserved_conversation_id": current,
        "observed_conversation_id": identity,
        "source": source,
        "at": utc_now(),
    }
    conflicts = state.setdefault("candidate_conversation_conflicts", [])
    if not any(
        item.get("preserved_conversation_id") == current
        and item.get("observed_conversation_id") == identity
        and item.get("source") == source
        for item in conflicts
    ):
        conflicts.append(conflict)
    state["candidate_conversation_conflict"] = True


def restore_legacy_candidate_evidence(state: dict[str, Any]) -> None:
    """Recover non-empty candidate evidence from fields and recorded status outputs."""
    for field, source in (
        ("candidate_conversation_id", "PERSISTED_CANDIDATE"),
        ("recovery_target_conversation_id", "LEGACY_RECOVERY_TARGET"),
        ("post_send_active_conversation_id", "LEGACY_POST_SEND_STATUS"),
        ("actual_delivery_conversation_id", "LEGACY_ACTUAL_DELIVERY"),
        ("ask_reported_conversation_id", "LEGACY_ASK_RESULT"),
    ):
        observe_candidate(state, state.get(field), source)
    for raw_value in state.get("raw_outputs", []):
        raw_path = Path(raw_value)
        if "status-after-send" not in raw_path.name or not raw_path.is_file():
            continue
        try:
            observed_url = status_url(read_json(raw_path))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            continue
        observed_id = conversation_id_from_url(observed_url or "")
        state["last_observed_status_conversation_id"] = observed_id
        observe_candidate(state, observed_id, f"LEGACY_RAW_STATUS:{raw_path.name}")


def marker(message_id: str) -> str:
    return f"MESSAGE_ID: {message_id}"


def has_exact_header(text: str, name: str, value: str) -> bool:
    if re.search(rf"(?m)^{re.escape(name)}:[ \t]*{re.escape(value)}[ \t]*\r?$", text):
        return True
    try:
        packet, _ = json.JSONDecoder().raw_decode(text.lstrip())
    except (json.JSONDecodeError, TypeError):
        return False
    return isinstance(packet, dict) and packet.get(name) == value


def inspect_messages(messages: list[dict[str, Any]], work_item_id: str, message_id: str) -> tuple[bool, bool, bool]:
    user_index: int | None = None
    for index, message in enumerate(messages):
        role = str(pick(message, "Role") or "").lower()
        text = str(pick(message, "Text") or "")
        if (
            role == "user"
            and has_exact_header(text, "MESSAGE_ID", message_id)
            and has_exact_header(text, "WORK_ITEM_ID", work_item_id)
        ):
            user_index = index
    if user_index is None:
        return False, False, False
    assistants = [message for message in messages[user_index + 1:] if str(pick(message, "Role") or "").lower() == "assistant"]
    if not assistants:
        return True, False, False
    latest = assistants[-1]
    text = str(pick(latest, "Text") or "").strip()
    generating = str(pick(latest, "Generating") or "false").lower() == "true"
    stable_value = pick(latest, "StableSeconds")
    try:
        stable = float(stable_value) >= STABLE_SECONDS if stable_value is not None else not generating
    except (TypeError, ValueError):
        stable = False
    return True, bool(text), bool(text) and not generating and stable


def exact_delivery_marker_count(
    messages: list[dict[str, Any]], work_item_id: str, message_id: str
) -> int:
    """Count exact outbound markers; delivery requires exactly one match."""
    return sum(
        1
        for message in messages
        if str(pick(message, "Role") or "").lower() == "user"
        and has_exact_header(str(pick(message, "Text") or ""), "MESSAGE_ID", message_id)
        and has_exact_header(str(pick(message, "Text") or ""), "WORK_ITEM_ID", work_item_id)
    )


COLLAPSED_PACKET_SUFFIX = "Show more"
COMPACT_PACKET_IDENTITY_PREFIX = re.compile(
    r'^\s*\{"WORK_ITEM_ID":(?P<work_item>"(?:\\.|[^"\\])*")'
    r',"MESSAGE_ID":(?P<message>"(?:\\.|[^"\\])*")'
)


def has_collapsed_packet_exact_identity(
    text: str, work_item_id: str, message_id: str,
) -> bool:
    """Verify Product packet identity without repairing collapsed message text."""
    if not text.rstrip().endswith(f"\n{COLLAPSED_PACKET_SUFFIX}"):
        return False
    match = COMPACT_PACKET_IDENTITY_PREFIX.match(text)
    if match is None:
        return False
    try:
        observed_work_item = json.loads(match.group("work_item"))
        observed_message = json.loads(match.group("message"))
    except (json.JSONDecodeError, TypeError):
        return False
    return observed_work_item == work_item_id and observed_message == message_id


def collapsed_delivery_marker_count(
    messages: list[dict[str, Any]], work_item_id: str, message_id: str,
) -> int:
    """Count exact compact-packet identities only when extraction says it collapsed."""
    return sum(
        1
        for message in messages
        if str(pick(message, "Role") or "").lower() == "user"
        and has_collapsed_packet_exact_identity(
            str(pick(message, "Text") or ""), work_item_id, message_id,
        )
    )


def rr_response_fields(
    text: str,
    expected_message_id: str | None = None,
    expected_work_item_id: str | None = None,
    expected_round: int | str | None = None,
) -> dict[str, str]:
    """Extract fields only from an exact RR review envelope."""
    lines = text.splitlines()
    nonempty = [index for index, line in enumerate(lines) if line.strip()]
    if not nonempty:
        return {}
    first, last = nonempty[0], nonempty[-1]
    if lines[first].strip() != RR_REVIEW_BEGIN or lines[last].strip() != RR_REVIEW_END:
        return {}
    body = lines[first + 1:last]
    if any(line.strip() in {RR_REVIEW_BEGIN, RR_REVIEW_END} for line in body):
        return {}

    fields: dict[str, str] = {}
    current: str | None = None
    blocks: dict[str, list[str]] = {}
    header = re.compile(r"^([A-Z][A-Z0-9_]*):(?:[ \t]*(.*))?\r?$")
    for line in body:
        match = header.fullmatch(line)
        if match:
            current = match.group(1)
            if current not in RR_ALLOWED_RESPONSE_FIELDS:
                return {"PROTOCOL_ERROR": f"UNKNOWN_TOP_LEVEL_FIELD:{current}"}
            if current in blocks:
                return {"REPLY_IDENTITY_ERROR": f"DUPLICATE_FIELD:{current}"}
            blocks[current] = [match.group(2) or ""]
        elif current is not None:
            blocks[current].append(line)
        elif line.strip():
            return {}
    for name, lines in blocks.items():
        value = "\n".join(lines).strip()
        if value:
            fields[name] = value

    canonical = fields.get("IN_REPLY_TO_MESSAGE_ID")
    alias = fields.pop(RR_REPLY_ID_ALIAS, None)
    if canonical is None and alias is None:
        fields["REPLY_IDENTITY_ERROR"] = "MISSING"
    elif alias is not None and alias != expected_message_id:
        fields["REPLY_IDENTITY_ERROR"] = "LEGACY_ALIAS_MISMATCH"
    elif canonical is not None and alias is not None and canonical != alias:
        fields["REPLY_IDENTITY_ERROR"] = "CANONICAL_ALIAS_CONFLICT"
    elif canonical is None:
        fields["IN_REPLY_TO_MESSAGE_ID"] = alias
        fields["REPLY_ID_SOURCE"] = "LEGACY_ALIAS"
    else:
        fields["REPLY_ID_SOURCE"] = "CANONICAL"

    response_message_id = fields.pop("MESSAGE_ID", None)
    if response_message_id is not None:
        expected_response_message_id = (
            f"{expected_work_item_id}-R{expected_round}-REVIEW"
            if expected_work_item_id is not None and expected_round is not None
            else None
        )
        if not response_message_id or response_message_id != expected_response_message_id:
            fields["REPLY_IDENTITY_ERROR"] = "RESPONSE_MESSAGE_ID_MISMATCH"
        else:
            fields["RESPONSE_MESSAGE_ID"] = response_message_id

    response_message_type = fields.pop("MESSAGE_TYPE", None)
    if response_message_type is not None:
        if response_message_type != "RR_REVIEW":
            fields["REPLY_IDENTITY_ERROR"] = "RESPONSE_MESSAGE_TYPE_MISMATCH"
        else:
            fields["RESPONSE_MESSAGE_TYPE"] = response_message_type
    return fields


def stable_assistant_text(message: dict[str, Any]) -> str | None:
    if str(pick(message, "Role") or "").lower() != "assistant":
        return None
    text = str(pick(message, "Text") or "").strip()
    generating = str(pick(message, "Generating") or "false").lower() == "true"
    stable_value = pick(message, "StableSeconds")
    try:
        stable = float(stable_value) >= STABLE_SECONDS if stable_value is not None else not generating
    except (TypeError, ValueError):
        stable = False
    return text if text and not generating and stable else None


def verify_rr_response_identity(
    messages: list[dict[str, Any]],
    response_source_conversation_id: str | None,
    verified_target_conversation_id: str | None,
    expected_work_item_id: str,
    last_sent_message_id: str,
    expected_round: int | str,
) -> dict[str, Any]:
    """Bind one complete Assistant review to its verified source and outbound message."""
    result: dict[str, Any] = {
        "status": "RESPONSE_PENDING",
        "review": None,
        "matching_response_count": 0,
        "outbound_message_found": False,
        "outbound_message_match_count": 0,
    }
    if (
        not response_source_conversation_id
        or not verified_target_conversation_id
        or response_source_conversation_id != verified_target_conversation_id
    ):
        result["status"] = "RESPONSE_SOURCE_CONVERSATION_MISMATCH"
        return result

    user_indexes: list[int] = []
    for index, message in enumerate(messages):
        if str(pick(message, "Role") or "").lower() != "user":
            continue
        text = str(pick(message, "Text") or "")
        if (
            has_exact_header(text, "WORK_ITEM_ID", expected_work_item_id)
            and has_exact_header(text, "MESSAGE_ID", last_sent_message_id)
        ):
            user_indexes.append(index)
    result["outbound_message_match_count"] = len(user_indexes)
    if not user_indexes:
        result["status"] = "RESPONSE_IDENTITY_MISMATCH"
        return result
    if len(user_indexes) > 1:
        result["status"] = "OUTBOUND_MESSAGE_IDENTITY_AMBIGUOUS"
        return result
    result["outbound_message_found"] = True
    user_index = user_indexes[0]

    complete: list[dict[str, str]] = []
    incomplete_seen = False
    identity_rejected_seen = False
    protocol_rejected_seen = False
    for message in messages[user_index + 1:]:
        text = stable_assistant_text(message)
        if text is None:
            continue
        fields = rr_response_fields(
            text, last_sent_message_id, expected_work_item_id, expected_round
        )
        if "PROTOCOL_ERROR" in fields:
            protocol_rejected_seen = True
        elif "REPLY_IDENTITY_ERROR" in fields:
            identity_rejected_seen = True
        elif set(RR_RESPONSE_FIELDS).issubset(fields):
            complete.append(fields)
        else:
            incomplete_seen = True

    matching = [
        fields for fields in complete
        if fields["WORK_ITEM_ID"] == expected_work_item_id
        and fields["IN_REPLY_TO_MESSAGE_ID"] == last_sent_message_id
        and fields["ROUND"] == str(expected_round)
    ]
    result["matching_response_count"] = len(matching)
    if len(matching) > 1:
        result["status"] = "RESPONSE_IDENTITY_AMBIGUOUS"
    elif len(matching) == 1:
        result["status"] = "RESPONSE_IDENTITY_VERIFIED"
        result["review"] = matching[0]
    elif protocol_rejected_seen:
        result["status"] = "RESPONSE_PROTOCOL_REJECTED"
    elif identity_rejected_seen:
        result["status"] = "RESPONSE_IDENTITY_REJECTED"
    elif incomplete_seen:
        result["status"] = "RESPONSE_IDENTITY_MISSING"
    elif complete:
        result["status"] = "RESPONSE_IDENTITY_MISMATCH"
    return result


def blank_new_url(url: str | None, old_id: str | None) -> bool:
    if not url:
        return False
    parsed = urlparse(url)
    if parsed.hostname not in {"chatgpt.com", "www.chatgpt.com"}:
        return False
    if conversation_id_from_url(url) or (old_id and old_id in url):
        return False
    return parsed.path in {"", "/", "/new"}


def prepare_state(args: argparse.Namespace, state_path: Path) -> dict[str, Any]:
    return {
        "schema_version": 7,
        "work_item_id": args.work_item_id,
        "operation": "PREPARE_NEW",
        "require_existing_conversation": bool(args.require_existing_conversation),
        "precondition_checked": False,
        "precondition_met": False,
        "pre_operation_url": None,
        "pre_operation_conversation_id": None,
        "pre_operation_mode": "UNKNOWN",
        "new_command_called": False,
        "post_operation_url": None,
        "conversation_transition_verified": False,
        "blank_environment_verified": False,
        "verification_result": "NOT_RUN",
        "read_result": "NOT_RUN",
        "message_send_count": 0,
        "external_command_count": 0,
        "placeholder_validation_performed": True,
        "unresolved_placeholders": [],
        "wrapper_schedule_call_count": 0,
        "agent_schedule_call_count": None,
        "total_schedule_call_count": None,
        "agent_bound_result_retrieval_count": None,
        "agent_tool_trace_verification": "UNAVAILABLE",
        "idle_wait_seconds": 0,
        "poll_attempt_count": 0,
        "background_result_check_count": 0,
        "background_wait_seconds": 0,
        "background_process_handle_support": False,
        "supported_wait_or_result_method": "NONE",
        "completion_mode": "NONE",
        "synchronous_command_completed": False,
        "terminated_immediately_after_result": False,
        "test_protocol_violation": False,
        "report_validation": "PASS",
        "started_at": PROCESS_STARTED_AT,
        "stopped_at": None,
        "elapsed_seconds": 0.0,
        "stop_reason": None,
        "test_result": None,
        "state_file": str(state_path),
        "raw_outputs": [],
        "parameters": {
            "max_send_attempts": PREPARE_MAX_SEND_ATTEMPTS,
            "max_recovery_attempts": PREPARE_MAX_RECOVERY_ATTEMPTS,
            "max_detail_checks": PREPARE_MAX_DETAIL_CHECKS,
            "max_external_commands": min(max(args.max_external_commands, 0), PREPARE_MAX_EXTERNAL_COMMANDS),
            "max_experiment_seconds": min(max(args.max_experiment_seconds, 0), MAX_EXPERIMENT_SECONDS),
            "command_wait_seconds": args.command_wait_seconds,
        },
    }


def finish_prepare(state: dict[str, Any], result: str, reason: str) -> None:
    state["test_result"] = result
    state["stop_reason"] = reason
    state["stopped_at"] = utc_now()
    state["elapsed_seconds"] = round(time.monotonic() - state["_monotonic_started"], 3)


def persist_prepare(state: dict[str, Any], state_path: Path) -> None:
    write_json(state_path, {key: value for key, value in state.items() if not key.startswith("_")})


def prepare_external_command(
    state: dict[str, Any], state_path: Path, label: str, args: list[str]
) -> dict[str, Any] | None:
    elapsed = time.monotonic() - state["_monotonic_started"]
    remaining = state["parameters"]["max_experiment_seconds"] - elapsed
    if state["external_command_count"] >= state["parameters"]["max_external_commands"] or remaining <= 0:
        finish_prepare(state, "BUDGET_EXHAUSTED", "BUDGET_EXHAUSTED")
        persist_prepare(state, state_path)
        return None
    state["terminated_immediately_after_result"] = False
    state["external_command_count"] += 1
    persist_prepare(state, state_path)
    result = run_opencli(args, max(0.001, min(state["parameters"]["command_wait_seconds"], remaining)))
    save_raw(state, state_path, label, result)
    if not result["timed_out"] and {"returncode", "stdout", "stderr"} <= result.keys():
        state["synchronous_command_completed"] = True
        state["terminated_immediately_after_result"] = True
        state["completion_mode"] = "SYNCHRONOUS_COMPLETION"
    persist_prepare(state, state_path)
    if result["timed_out"] or time.monotonic() - state["_monotonic_started"] >= state["parameters"]["max_experiment_seconds"]:
        finish_prepare(state, "BUDGET_EXHAUSTED", "BUDGET_EXHAUSTED")
        persist_prepare(state, state_path)
        return None
    return result


def prepare_new_command(args: argparse.Namespace) -> int:
    unresolved = unresolved_required_values({
        "RUNTIME_DIR": args.runtime_dir,
        "WORK_ITEM_ID": args.work_item_id,
    })
    if unresolved:
        report = assess_experiment_protocol(
            {"RUNTIME_DIR": args.runtime_dir, "WORK_ITEM_ID": args.work_item_id}, []
        )
        report.update({
            "operation": "PREPARE_NEW",
            "message_send_count": 0,
            "stop_reason": "REQUIRED_VALUE_UNRESOLVED",
            "test_result": "BLOCKED_BEFORE_EXECUTION",
        })
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 2
    runtime_dir = Path(args.runtime_dir).resolve()
    state_path = runtime_dir / "prepare-new-state.json"
    if state_path.exists():
        existing = read_json(state_path)
        existing["test_result"] = "TEST_PROTOCOL_VIOLATION"
        existing["stop_reason"] = "TEST_PROTOCOL_VIOLATION"
        existing["stopped_at"] = utc_now()
        existing["elapsed_seconds"] = round(time.monotonic() - PROCESS_MONOTONIC_STARTED, 3)
        write_json(state_path, existing)
        print(json.dumps(existing, ensure_ascii=False, indent=2, sort_keys=True))
        return 2
    state = prepare_state(args, state_path)
    state["_monotonic_started"] = PROCESS_MONOTONIC_STARTED
    persist_prepare(state, state_path)

    pre_status = prepare_external_command(
        state, state_path, "status-before-prepare",
        ["chatgpt", "status", "-f", "json", "--window", "background"],
    )
    if pre_status is not None:
        state["precondition_checked"] = True
        state["pre_operation_url"] = status_url(pre_status)
        state["pre_operation_conversation_id"] = existing_chatgpt_conversation_id(
            state["pre_operation_url"]
        )
        if state["pre_operation_conversation_id"]:
            state["pre_operation_mode"] = "EXISTING_CONVERSATION"
            state["precondition_met"] = True
        elif blank_new_url(state["pre_operation_url"], None):
            state["pre_operation_mode"] = "ALREADY_NEW"
        persist_prepare(state, state_path)
    if pre_status is not None and (
        pre_status["timed_out"] or pre_status["returncode"] != 0 or not state["pre_operation_url"]
    ):
        finish_prepare(state, "BLOCKED_BEFORE_SEND", "PRE_OPERATION_STATUS_UNVERIFIED")
        persist_prepare(state, state_path)
        pre_status = None
    if (
        pre_status is not None
        and state["require_existing_conversation"]
        and not state["precondition_met"]
    ):
        finish_prepare(
            state,
            "BLOCKED_BEFORE_EXECUTION",
            "EXISTING_CONVERSATION_PRECONDITION_NOT_MET",
        )
        persist_prepare(state, state_path)
        pre_status = None
    before_new_count = state["external_command_count"]
    created = None if pre_status is None else prepare_external_command(
        state, state_path, "new",
        ["chatgpt", "new", "-f", "json", "--window", "background"],
    )
    state["new_command_called"] = state["external_command_count"] > before_new_count
    persist_prepare(state, state_path)
    created_ok = bool(result_rows(created))
    post_status = None if not created_ok else prepare_external_command(
        state, state_path, "status-after-prepare",
        ["chatgpt", "status", "-f", "json", "--window", "background"],
    )
    if post_status is not None:
        state["post_operation_url"] = status_url(post_status)
        if blank_new_url(state["post_operation_url"], state["pre_operation_conversation_id"]):
            state["verification_result"] = "NEW_BLANK_URL_VERIFIED"
            state["conversation_transition_verified"] = (
                state["pre_operation_mode"] == "EXISTING_CONVERSATION"
            )
        else:
            state["verification_result"] = "FAILED"
        persist_prepare(state, state_path)
    read = None
    if state.get("test_result") is None and state["verification_result"] == "NEW_BLANK_URL_VERIFIED":
        read = prepare_external_command(
            state, state_path, "read-new",
            ["chatgpt", "read", "-f", "json", "--window", "background"],
        )
    if read is not None:
        classification = classify_chatgpt_read_result(read)
        if classification == "EMPTY":
            state["read_result"] = "EMPTY"
            state["verification_result"] = "NEW_BLANK_CONVERSATION_VERIFIED"
            state["blank_environment_verified"] = True
            finish_prepare(state, "PREPARED_NEW_CONVERSATION", "STOP_WITHOUT_SEND")
        elif classification == "NON_EMPTY":
            state["read_result"] = "NON_EMPTY"
            finish_prepare(state, "BLOCKED_BEFORE_SEND", "READ_NOT_EMPTY")
        else:
            state["read_result"] = "UNPARSEABLE"
            finish_prepare(state, "BLOCKED_BEFORE_SEND", "READ_UNPARSEABLE")
    elif state.get("test_result") is None:
        state["read_result"] = "NOT_RUN"
        finish_prepare(state, "BLOCKED_BEFORE_SEND", "NEW_CONVERSATION_VERIFICATION_FAILED")

    public_state = {key: value for key, value in state.items() if not key.startswith("_")}
    persist_prepare(state, state_path)
    print(json.dumps(public_state, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if public_state["test_result"] == "PREPARED_NEW_CONVERSATION" else 2


def prepare_payload(args: argparse.Namespace, body: str) -> str:
    if has_exact_header(body, "MESSAGE_ID", args.message_id):
        raise ValueError("message body already contains MESSAGE_ID; provide body without transport headers")
    return json.dumps({
        "WORK_ITEM_ID": args.work_item_id,
        "MESSAGE_ID": args.message_id,
        "ROUND": args.round,
        "MESSAGE_TYPE": args.message_type,
        "SHARED_OBJECTIVE": "See EVIDENCE.",
        "ACCEPTANCE_CRITERIA": "See EVIDENCE.",
        "EVIDENCE": body.lstrip("\ufeff"),
        "RR_LEAD_QUESTION": "Follow the request in EVIDENCE.",
        "END_SENTINEL": f"RR-PACKET-COMPLETE:{args.message_id}",
    }, ensure_ascii=False, separators=(",", ":"))


def read_payload(args: argparse.Namespace) -> str:
    if args.message_file:
        return Path(args.message_file).read_text(encoding="utf-8")
    if sys.stdin.isatty():
        raise ValueError("provide message content on stdin or with --message-file")
    return sys.stdin.read()


def strict_utf8_text(path: Path) -> str:
    """Strictly decode one UTF-8 file; reject invalid bytes and lone surrogates.

    Reads raw bytes and decodes without an errors fallback so invalid sequences
    raise before any send. A following strict re-encode rejects lone surrogates
    that survive decoding, so corrupted characters are never silently replaced.
    """
    if not path.is_file():
        raise ValueError(f"required file does not exist: {path}")
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"invalid UTF-8 in {path}: {error}") from error
    try:
        text.encode("utf-8")
    except UnicodeEncodeError as error:
        raise ValueError(f"lone surrogate in {path}: {error}") from error
    text = text.removeprefix("\ufeff")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def bootstrap_body(args: argparse.Namespace) -> str:
    """Deterministically assemble the init and context files into one body."""
    nl = "\n"
    init_text = strict_utf8_text(Path(args.init_file))
    context_text = strict_utf8_text(Path(args.context_file))
    body = (
        f"{BOOTSTRAP_BEGIN_INIT}{nl}"
        f"{init_text.rstrip(nl)}{nl}"
        f"{BOOTSTRAP_END_INIT}{nl}{nl}"
        f"{BOOTSTRAP_BEGIN_CONTEXT}{nl}"
        f"{context_text.rstrip(nl)}{nl}"
        f"{BOOTSTRAP_END_CONTEXT}"
    )
    for marker in (
        BOOTSTRAP_BEGIN_INIT, BOOTSTRAP_END_INIT,
        BOOTSTRAP_BEGIN_CONTEXT, BOOTSTRAP_END_CONTEXT,
    ):
        if body.splitlines().count(marker) != 1:
            raise ValueError(f"bootstrap boundary is not unique: {marker}")
    return body


def new_state(args: argparse.Namespace, state_path: Path) -> dict[str, Any]:
    started = utc_now()
    return {
        "schema_version": 5, "work_item_id": args.work_item_id, "message_id": args.message_id,
        "operation": "START_NEW_AND_SEND" if args.prepare_new else "SEND",
        "prepare_new": bool(args.prepare_new),
        "round": args.round, "message_type": args.message_type,
        "expected_conversation_mode": "EXISTING" if args.conversation else "NEW",
        "created_conversation_id": None,
        "target_conversation_id": args.conversation,
        "target_conversation_id_at_send": args.conversation,
        "current_browser_conversation_id": None,
        "delivery_conversation_id": None,
        "recovered_conversation_id": None,
        "target_binding_mode": "EXISTING_EXPLICIT" if args.conversation else "NEW_SESSION_FIRST_WRITE",
        "identity_observations": [],
        "identity_establishment": {},
        "delivery_marker_status": "NOT_CHECKED",
        "pre_send_active_conversation_id": None, "verified_target_conversation_id": None,
        "actual_delivery_conversation_id": None, "verified_target_url": None,
        "delivery_state": "NOT_SENT", "work_item_state": "IN_PROGRESS",
        "send_attempted": False,
        "send_attempt_count": 0, "message_send_count": 0,
        "recovery_attempt_count": 0,
        "automatic_recovery_attempt_count": 0,
        "manual_recovery_attempt_count": 0,
        "detail_check_count": 0,
        "external_command_count": 0, "misroute_detected": False,
        "read_result": "NOT_RUN", "blank_environment_verified": False,
        "pre_send_already_new": False, "new_command_called": False,
        "browser_navigation_occurred": False,
        "official_response_eligible": False,
        "response_identity_status": "RESPONSE_PENDING",
        "response_source_conversation_id": None,
        "response_source_kind": None,
        "response_raw_output_path": None,
        "verified_rr_review": None,
        "started_at": started, "original_send_started_at": started,
        "current_operation": "SEND", "current_operation_started_at": started,
        "current_operation_external_command_count": 0,
        "manual_recover_started_at": None,
        "manual_recover_external_command_count": 0,
        "pending_response_continuation_count": 0,
        "late_response_check_count": 0,
        "pending_response_window_seconds": TOTAL_RESPONSE_WAIT_SECONDS,
        "pending_response_last_checked_at": None,
        "pending_response_last_result": None,
        "stopped_at": None,
        "stop_reason": None, "updated_at": utc_now(), "state_file": str(state_path),
        "raw_outputs": [], "transitions": [],
        "post_send_status_url": None, "post_send_active_conversation_id": None,
        "post_send_page_mode": "NOT_RUN", "post_send_history_called": False,
        "post_send_history_available": False, "post_send_recent_conversation_ids": [],
        "new_candidate_diff": [], "recovery_target_source": None,
        "recovery_target_conversation_id": None,
        "candidate_conversation_id": None,
        "candidate_conversation_source": None,
        "candidate_conversation_conflict": False,
        "candidate_conversation_conflicts": [],
        "last_observed_status_conversation_id": None,
        "navigation_wait_started_at": None,
        "navigation_wait_deadline": None,
        "navigation_wait_elapsed": 0.0,
        "navigation_poll_count": 0,
        "navigation_status_attempt_count": 0,
        "navigation_status_success_count": 0,
        "navigation_status_error_count": 0,
        "navigation_completion_url": None,
        "navigation_completion_conversation_id": None,
        "navigation_wait_stop_reason": None,
        "operation_budget_excluded_navigation_seconds": 0.0,
        "parameters": {
            "command_wait_seconds": args.command_wait_seconds,
            "max_send_attempts_per_message": MAX_SEND_ATTEMPTS_PER_MESSAGE,
            "max_recovery_attempts": args.max_recovery_attempts,
            "max_detail_checks": args.max_detail_checks,
            "max_external_commands": args.max_external_commands,
            "max_experiment_seconds": args.max_experiment_seconds,
            "max_post_send_navigation_wait_seconds": min(
                max(float(getattr(
                    args, "max_post_send_navigation_wait_seconds",
                    MAX_POST_SEND_NAVIGATION_WAIT_SECONDS,
                )), 0.0),
                MAX_POST_SEND_NAVIGATION_WAIT_SECONDS,
            ),
            "max_navigation_status_checks": min(
                max(int(getattr(
                    args, "max_navigation_status_checks",
                    MAX_NAVIGATION_STATUS_CHECKS,
                )), 0),
                MAX_NAVIGATION_STATUS_CHECKS,
            ),
            "post_send_navigation_poll_interval_seconds": min(
                max(float(getattr(
                    args, "post_send_navigation_poll_interval_seconds",
                    POST_SEND_NAVIGATION_POLL_INTERVAL_SECONDS,
                )), 0.1),
                POST_SEND_NAVIGATION_POLL_INTERVAL_SECONDS,
            ),
            "recent_candidate_limit": args.recent_candidate_limit,
            "max_pending_response_continuations": MAX_PENDING_RESPONSE_CONTINUATIONS,
            "pending_response_wait_window_seconds": TOTAL_RESPONSE_WAIT_SECONDS,
        },
    }


def history_result(
    state: dict[str, Any], state_path: Path, label: str = "history"
) -> tuple[list[dict[str, Any]], bool]:
    result = command(state, state_path, label, ["chatgpt", "history", "--limit", str(state["parameters"]["recent_candidate_limit"]), "-f", "json", "--window", "background"], state["parameters"]["command_wait_seconds"])
    available = bool(
        result is not None
        and not result["timed_out"]
        and result["returncode"] == 0
        and isinstance(parse_json(result["stdout"]), list)
    )
    return result_rows(result), available


def history(state: dict[str, Any], state_path: Path) -> list[dict[str, Any]]:
    return history_result(state, state_path)[0]


def detail(
    state: dict[str, Any], state_path: Path, identity: str
) -> ResponseMessageBatch | None:
    if state["detail_check_count"] >= state["parameters"]["max_detail_checks"]:
        return None
    before_command_count = state["external_command_count"]
    result = command(state, state_path, "detail", ["chatgpt", "detail", identity, "-f", "json", "--window", "background"], state["parameters"]["command_wait_seconds"])
    if state["external_command_count"] > before_command_count:
        state["detail_check_count"] += 1
    raw = state["raw_outputs"][-1] if result is not None else None
    if result is None:
        return None
    return ResponseMessageBatch(
        conversation_id=identity,
        messages=tuple(result_rows(result)),
        source_kind="DETAIL_RESULT",
        raw_output_path=raw,
    )


def response_batch_from_ask(
    result: dict[str, Any], payload: str, raw_output_path: str | None
) -> ResponseMessageBatch | None:
    """Bind identity and response extracted from the same ask result."""
    identity, _ = ask_identity(result)
    response = ask_response(result)
    if not identity or not response:
        return None
    return ResponseMessageBatch(
        conversation_id=identity,
        messages=(
            {"Role": "user", "Text": payload},
            {"Role": "assistant", "Text": response, "Generating": False},
        ),
        source_kind="ASK_RESULT",
        raw_output_path=raw_output_path,
    )


def establish_verified_target(state: dict[str, Any], identity: str) -> bool:
    """Establish a target once; never replace a conflicting verified target."""
    current = state.get("verified_target_conversation_id")
    if current and current != identity:
        return False
    state["verified_target_conversation_id"] = identity
    return True


def record_identity_observation(
    state: dict[str, Any], role: str, identity: str | None, source_kind: str,
    raw_output_path: str | None = None,
) -> None:
    if not identity:
        return
    state.setdefault("identity_observations", []).append({
        "role": role,
        "value": identity,
        "source_kind": source_kind,
        "observed_at": utc_now(),
        "raw_output_path": raw_output_path,
        "work_item_id": state.get("work_item_id"),
        "message_id": state.get("message_id"),
    })


def establish_identity(
    state: dict[str, Any], role: str, identity: str, source_kind: str,
    raw_output_path: str | None = None, *, exact_marker_verified: bool = False,
) -> bool:
    field = f"{role.lower()}_conversation_id"
    existing = state.setdefault("identity_establishment", {}).get(role)
    if existing and existing.get("value") != identity:
        state.setdefault("identity_establishment_conflicts", []).append({
            "role": role,
            "preserved_value": existing.get("value"),
            "rejected_value": identity,
            "source_kind": source_kind,
            "observed_at": utc_now(),
        })
        return False
    state[field] = identity
    record = {
        "value": identity,
        "source_kind": source_kind,
        "established_at": utc_now(),
        "raw_output_path": raw_output_path,
        "work_item_id": state.get("work_item_id"),
        "message_id": state.get("message_id"),
    }
    if role == "DELIVERY":
        record["exact_marker_verified"] = exact_marker_verified
        state["actual_delivery_conversation_id"] = identity
    state["identity_establishment"][role] = record
    return True


def ensure_identity_schema(state: dict[str, Any]) -> dict[str, Any]:
    """Conservatively expose v5 identity roles without upgrading candidates to facts."""
    if state.get("schema_version", 0) >= 5:
        return state
    legacy_version = state.get("schema_version")
    state["legacy_schema_version"] = legacy_version
    state["schema_version"] = 5
    state.setdefault("created_conversation_id", None)
    legacy_target = (
        state.get("verified_target_conversation_id")
        if state.get("expected_conversation_mode") == "EXISTING"
        else None
    )
    state.setdefault("target_conversation_id", legacy_target)
    state.setdefault("target_conversation_id_at_send", legacy_target)
    state.setdefault(
        "current_browser_conversation_id",
        state.get("post_send_active_conversation_id")
        or state.get("last_observed_status_conversation_id")
        or state.get("pre_send_active_conversation_id"),
    )
    state.setdefault("delivery_conversation_id", None)
    state.setdefault("recovered_conversation_id", None)
    state.setdefault(
        "target_binding_mode",
        "EXISTING_EXPLICIT" if legacy_target else "NEW_SESSION_FIRST_WRITE",
    )
    state.setdefault("identity_observations", [])
    state.setdefault("identity_establishment", {})
    state.setdefault("delivery_marker_status", "NOT_CHECKED")
    state.setdefault("migration_notes", []).append(
        "Legacy delivery/recovery identities retained as candidates pending exact-marker re-verification."
    )
    return state


def establish_verified_delivery(
    state: dict[str, Any], response_batch: ResponseMessageBatch,
    verified_marker_count: int | None = None,
) -> bool:
    """Establish delivery only from one exact marker and a non-conflicting identity."""
    identity = response_batch.conversation_id
    marker_count = (
        verified_marker_count
        if verified_marker_count is not None
        else exact_delivery_marker_count(
            list(response_batch.messages), state["work_item_id"], state["message_id"]
        )
    )
    state["delivery_marker_count"] = marker_count
    state["delivery_marker_status"] = (
        "UNIQUE" if marker_count == 1 else "MISSING" if marker_count == 0 else "DUPLICATE"
    )
    if marker_count != 1:
        return False
    target_at_send = state.get("target_conversation_id_at_send")
    if not target_at_send and identity in pre_send_ids(state):
        establish_identity(
            state, "DELIVERY", identity, response_batch.source_kind,
            response_batch.raw_output_path, exact_marker_verified=True,
        )
        mark_misroute(state, identity, response_batch.raw_output_path)
        return False
    if target_at_send and target_at_send != identity:
        establish_identity(
            state, "DELIVERY", identity, response_batch.source_kind,
            response_batch.raw_output_path, exact_marker_verified=True,
        )
        mark_misroute(state, identity, response_batch.raw_output_path)
        return False
    establish_identity(
        state, "DELIVERY", identity, response_batch.source_kind,
        response_batch.raw_output_path, exact_marker_verified=True,
    )
    if not target_at_send:
        establish_identity(
            state, "TARGET", identity, "PROMOTED_FROM_VERIFIED_DELIVERY",
            response_batch.raw_output_path,
        )
        state["target_binding_mode"] = "PROMOTED_VERIFIED_DELIVERY"
    establish_verified_target(state, identity)
    return True


def mark_misroute(state: dict[str, Any], identity: str, raw_path: str | None) -> None:
    state["actual_delivery_conversation_id"] = identity
    state["misroute_detected"] = True
    state["official_response_eligible"] = False
    state["misroute_evidence"] = {"conversation_id": identity, "raw_path": raw_path,
                                  "matched_work_item_id": state["work_item_id"], "matched_message_id": state["message_id"]}
    set_state(state, "MISROUTED_DELIVERY", "exact marker found in a Conversation different from the send target")
    stop(state, "MISROUTED_DELIVERY: do not resend this Message ID", "IN_PROGRESS")


def pre_send_ids(state: dict[str, Any]) -> set[str]:
    identities = set(state.get("pre_send_recent_conversation_ids", []))
    if state.get("pre_send_active_conversation_id"):
        identities.add(state["pre_send_active_conversation_id"])
    return identities


def verify_persisted_continuation_target(
    state: dict[str, Any], state_path: Path, proof_path: Path, target: str,
) -> bool:
    """Verify one previously established delivery through its exact ID and marker."""
    try:
        previous = ensure_identity_schema(read_json(proof_path))
    except (OSError, ValueError, json.JSONDecodeError):
        state["known_target_verification"] = "INVALID_PROOF_STATE"
        return False
    previous_delivery = previous.get("delivery_conversation_id")
    previous_target = previous.get("target_conversation_id")
    establishment = previous.get("identity_establishment", {}).get("DELIVERY", {})
    proof_valid = bool(
        previous.get("work_item_id") == state.get("work_item_id")
        and previous.get("delivery_state") in {"DELIVERED", "RESPONSE_PENDING", "RESPONSE_READY"}
        and previous_delivery == target
        and previous_target == target
        and previous.get("send_attempt_count") == 1
        and establishment.get("value") == target
        and establishment.get("exact_marker_verified") is True
        and isinstance(previous.get("message_id"), str)
        and previous.get("message_id")
    )
    if not proof_valid:
        state["known_target_verification"] = "INVALID_PROOF_STATE"
        return False

    result = command(
        state,
        state_path,
        "verify-known-continuation-target",
        ["chatgpt", "detail", target, "-f", "json", "--window", "background"],
        state["parameters"]["command_wait_seconds"],
    )
    marker_count = exact_delivery_marker_count(
        result_rows(result), previous["work_item_id"], previous["message_id"]
    )
    state["known_target_proof_state"] = str(proof_path.resolve())
    state["known_target_proof_message_id"] = previous["message_id"]
    state["known_target_exact_marker_count"] = marker_count
    state["known_target_verification"] = (
        "EXACT_IDENTITY_VERIFIED" if marker_count == 1 else "EXACT_IDENTITY_UNVERIFIED"
    )
    if marker_count != 1:
        return False
    record_identity_observation(
        state, "TARGET", target, "PERSISTED_DELIVERY_EXACT_DETAIL",
        state["raw_outputs"][-1] if result is not None else None,
    )
    return True


def accept_delivery(state: dict[str, Any], response_batch: ResponseMessageBatch) -> None:
    state["actual_delivery_conversation_id"] = response_batch.conversation_id
    state["response_source_conversation_id"] = response_batch.conversation_id
    state["response_source_kind"] = response_batch.source_kind
    state["response_raw_output_path"] = response_batch.raw_output_path
    identity_result = verify_rr_response_identity(
        list(response_batch.messages),
        response_batch.conversation_id,
        state["verified_target_conversation_id"],
        state["work_item_id"],
        state["message_id"],
        state["round"],
    )
    response_status = identity_result["status"]
    state["response_identity_status"] = response_status
    state["verified_rr_review"] = identity_result["review"]
    state["official_response_eligible"] = response_status == "RESPONSE_IDENTITY_VERIFIED"
    if state["official_response_eligible"]:
        set_state(state, "RESPONSE_READY", "RR response source, role, order, and content identity verified")
        stop(state, "RESPONSE_READY", "ACHIEVED")
    else:
        set_state(state, response_status, "delivery confirmed but no unique identity-bound RR response was accepted")
        stop(state, f"{response_status}: same Message ID resend remains forbidden", "IN_PROGRESS")


def capture_post_send_status(
    state: dict[str, Any], state_path: Path
) -> dict[str, Any] | None:
    status = command(state, state_path, "status-after-send", ["chatgpt", "status", "-f", "json", "--window", "background"], state["parameters"]["command_wait_seconds"])
    apply_post_send_status(state, status, "POST_SEND_STATUS")
    return status


def apply_post_send_status(
    state: dict[str, Any], status: dict[str, Any] | None, source_kind: str,
) -> tuple[str | None, str | None]:
    current_url = status_url(status)
    current_id = conversation_id_from_url(current_url or "")
    state["last_observed_status_conversation_id"] = current_id
    if current_url:
        state["post_send_status_url"] = current_url
    if current_id:
        state["post_send_active_conversation_id"] = current_id
        state["current_browser_conversation_id"] = current_id
        record_identity_observation(
            state, "CURRENT_BROWSER", current_id, source_kind,
            state["raw_outputs"][-1] if status is not None else None,
        )
    observe_candidate(state, current_id, source_kind)
    state["post_send_page_mode"] = page_mode(current_url)
    return current_url, current_id


def wait_for_post_send_navigation(
    state: dict[str, Any], state_path: Path,
) -> dict[str, Any] | None:
    """Observe NEW-session URL completion without consuming the write/recovery budgets."""
    state["navigation_wait_started_at"] = utc_now()
    started = time.monotonic()
    configured = state["parameters"]["max_post_send_navigation_wait_seconds"]
    wait_budget = float(configured)
    deadline_at = datetime.now(timezone.utc).timestamp() + wait_budget
    state["navigation_wait_deadline"] = datetime.fromtimestamp(
        deadline_at, timezone.utc,
    ).isoformat(timespec="seconds")
    interval = state["parameters"]["post_send_navigation_poll_interval_seconds"]
    max_attempts = state["parameters"]["max_navigation_status_checks"]
    state["navigation_wait_budget_seconds"] = round(wait_budget, 3)
    write_json(state_path, state)

    while True:
        elapsed = time.monotonic() - started
        state["navigation_wait_elapsed"] = round(elapsed, 3)
        state["operation_budget_excluded_navigation_seconds"] = round(elapsed, 3)
        remaining = wait_budget - elapsed
        if remaining <= 0:
            state["navigation_wait_stop_reason"] = (
                "STATUS_OBSERVATION_NOT_EXECUTED_DUE_TO_DEADLINE"
            )
            write_json(state_path, state)
            return None
        minimum_status_budget = min(
            float(state["parameters"]["command_wait_seconds"]),
            float(MIN_NAVIGATION_STATUS_COMMAND_BUDGET_SECONDS),
        )
        if remaining < minimum_status_budget:
            state["navigation_wait_stop_reason"] = (
                "STATUS_OBSERVATION_NOT_EXECUTED_DUE_TO_DEADLINE_BUDGET"
            )
            write_json(state_path, state)
            return None
        if state["navigation_status_attempt_count"] >= max_attempts:
            state["navigation_wait_stop_reason"] = (
                "STATUS_OBSERVATION_NOT_EXECUTED_DUE_TO_ATTEMPT_BUDGET"
            )
            write_json(state_path, state)
            return None
        time.sleep(min(float(interval), remaining))
        elapsed = time.monotonic() - started
        state["navigation_wait_elapsed"] = round(elapsed, 3)
        state["operation_budget_excluded_navigation_seconds"] = round(elapsed, 3)
        remaining = wait_budget - elapsed
        if remaining <= 0:
            state["navigation_wait_stop_reason"] = (
                "STATUS_OBSERVATION_NOT_EXECUTED_DUE_TO_DEADLINE"
            )
            write_json(state_path, state)
            return None

        state["external_command_count"] += 1
        state["navigation_status_attempt_count"] += 1
        state["navigation_poll_count"] += 1
        timeout = min(
            float(state["parameters"]["command_wait_seconds"]),
            remaining,
        )
        result = run_opencli(
            ["chatgpt", "status", "-f", "json", "--window", "background"],
            timeout,
        )
        save_raw(
            state, state_path,
            f"status-navigation-{state['navigation_poll_count']}", result,
        )
        state["navigation_wait_elapsed"] = round(time.monotonic() - started, 3)
        state["operation_budget_excluded_navigation_seconds"] = state[
            "navigation_wait_elapsed"
        ]
        if result.get("timed_out") or result.get("returncode") != 0:
            state["navigation_status_error_count"] += 1
            state["navigation_wait_stop_reason"] = "ACTUAL_STATUS_COMMAND_ERROR"
            write_json(state_path, state)
            return None
        state["navigation_status_success_count"] += 1
        current_url, current_id = apply_post_send_status(
            state, result, "POST_SEND_NAVIGATION_STATUS",
        )
        mode = page_mode(current_url)
        if current_id:
            state["navigation_completion_url"] = current_url
            state["navigation_completion_conversation_id"] = current_id
            state["navigation_wait_stop_reason"] = "EXACT_CONVERSATION_ID_OBSERVED"
            write_json(state_path, state)
            return result
        if mode not in {"NEW", "ROOT"}:
            state["navigation_wait_stop_reason"] = "INVALID_NAVIGATION_IDENTITY"
            write_json(state_path, state)
            return None
        write_json(state_path, state)


def recovery_attempt_key(recovery_kind: str) -> str:
    if recovery_kind == "automatic":
        return "automatic_recovery_attempt_count"
    if recovery_kind == "manual":
        return "manual_recovery_attempt_count"
    raise ValueError(f"unsupported recovery kind: {recovery_kind}")


def recovery_budget_available(state: dict[str, Any], recovery_kind: str) -> bool:
    key = recovery_attempt_key(recovery_kind)
    return state.get(key, 0) < state["parameters"]["max_recovery_attempts"]


def record_recovery_attempt(state: dict[str, Any], recovery_kind: str) -> None:
    key = recovery_attempt_key(recovery_kind)
    state[key] = state.get(key, 0) + 1
    separated_total = (
        state.get("automatic_recovery_attempt_count", 0)
        + state.get("manual_recovery_attempt_count", 0)
    )
    state["recovery_attempt_count"] = max(
        state.get("recovery_attempt_count", 0), separated_total
    )


def recover_delivery(
    state: dict[str, Any], state_path: Path,
    returned_identity: str | None = None,
    post_send_status: dict[str, Any] | None = None,
    post_send_status_checked: bool = False,
    recovery_kind: str = "automatic",
) -> bool:
    if not recovery_budget_available(state, recovery_kind):
        if recovery_kind == "automatic":
            # Automatic transport cannot recover within budget: hand the
            # prepared payload to a human for Manual Relay instead of
            # permanently failing the Work Item.
            if state.get("send_attempt_count", 0) >= 1:
                set_state(
                    state,
                    "DELIVERY_UNKNOWN",
                    "automatic recovery budget exhausted after write; same Message ID remains no-resend",
                )
                stop(state, "DELIVERY_UNKNOWN: do not resend or manual-relay this Message ID", "IN_PROGRESS")
            else:
                set_state(
                    state,
                    "MANUAL_RELAY_REQUIRED",
                    "automatic recovery budget exhausted before write; use manual-export to relay",
                )
                state["work_item_state"] = "IN_PROGRESS"
        else:
            stop(
                state,
                f"EXPERIMENT_BUDGET_EXHAUSTED: MAX_{recovery_kind.upper()}_RECOVERY_ATTEMPTS",
            )
        return False
    record_recovery_attempt(state, recovery_kind)
    restore_legacy_candidate_evidence(state)
    candidates: list[tuple[str, str]] = []
    status = post_send_status if post_send_status_checked else capture_post_send_status(state, state_path)
    current_url = status_url(status)
    current_id = conversation_id_from_url(current_url or "")
    before_history_count = state["external_command_count"]
    if current_id:
        post_rows, history_available = [], False
    else:
        post_rows, history_available = history_result(state, state_path, "history-after-send")
    state["post_send_history_called"] = state["external_command_count"] > before_history_count
    state["post_send_history_available"] = history_available
    post_ids = [identity for row in post_rows if (identity := conversation_identity(row)[0])]
    baseline = pre_send_ids(state)
    new_ids = [identity for identity in post_ids if identity not in baseline]
    state["post_send_recent_conversation_ids"] = post_ids
    state["new_candidate_diff"] = new_ids

    def add_candidate(identity: str | None, source: str) -> None:
        if identity and all(existing != identity for existing, _ in candidates):
            candidates.append((identity, source))

    explicit_target = state.get("target_conversation_id_at_send")
    if explicit_target:
        add_candidate(explicit_target, "PERSISTED_TARGET_AT_SEND")
    else:
        add_candidate(
            state.get("candidate_conversation_id"),
            state.get("candidate_conversation_source") or "PERSISTED_CANDIDATE",
        )
        add_candidate(returned_identity, "SEND_REPORTED_CONVERSATION_ID")
        add_candidate(current_id, "POST_SEND_STATUS")
        if len(new_ids) == 1:
            add_candidate(new_ids[0], "POST_SEND_HISTORY_NEW_CANDIDATE_DIFF")
        elif len(new_ids) > 1 and not candidates:
            state["recovery_target_source"] = "AMBIGUOUS_NEW_CANDIDATE_DIFF"
    unique_candidate_ids = {identity for identity, _ in candidates}
    if (not explicit_target and state.get("candidate_conversation_conflict")) or len(unique_candidate_ids) > 1:
        state["recovery_target_source"] = "IDENTITY_CONFLICT"
        if not state.get("stopped_at"):
            set_state(state, "DELIVERY_UNKNOWN", "bounded recovery found conflicting identity candidates")
            stop(state, "DELIVERY_UNKNOWN: do not resend this Message ID", "IN_PROGRESS")
        return False
    if candidates:
        identity, source = candidates[0]
        observe_candidate(state, identity, source)
        state["recovery_target_source"] = source
        state["recovery_target_conversation_id"] = identity
        establish_identity(state, "RECOVERED", identity, source)
        response_batch = detail(state, state_path, identity)
        messages = list(response_batch.messages) if response_batch else []
        marker_count = exact_delivery_marker_count(messages, state["work_item_id"], state["message_id"])
        if (
            marker_count == 0
            and response_batch is not None
            and state.get("send_attempt_count") == 1
            and state.get("message_send_count") == 1
            and state.get("recovered_conversation_id") == response_batch.conversation_id
            and state.get("recovery_target_conversation_id") == response_batch.conversation_id
        ):
            collapsed_count = collapsed_delivery_marker_count(
                messages, state["work_item_id"], state["message_id"],
            )
            state["truncation_evidence_detected"] = any(
                str(pick(message, "Text") or "").rstrip().endswith(
                    f"\n{COLLAPSED_PACKET_SUFFIX}"
                )
                for message in messages
                if str(pick(message, "Role") or "").lower() == "user"
            )
            state["truncation_fallback_marker_count"] = collapsed_count
            state["truncation_fallback_status"] = (
                "UNIQUE" if collapsed_count == 1
                else "MISSING" if collapsed_count == 0
                else "DUPLICATE"
            )
            if collapsed_count == 1:
                marker_count = collapsed_count
                state["delivery_verification_mode"] = "EXACT_ID_COLLAPSED_PACKET_IDENTITY"
        if marker_count == 1:
            if state.get("target_conversation_id_at_send") and identity != state["target_conversation_id_at_send"]:
                mark_misroute(
                    state, identity,
                    response_batch.raw_output_path if response_batch else None,
                )
            else:
                if response_batch is not None and establish_verified_delivery(
                    state, response_batch, verified_marker_count=marker_count,
                ):
                    accept_delivery(state, response_batch)
            return True
        state["delivery_marker_count"] = marker_count
        state["delivery_marker_status"] = "MISSING" if marker_count == 0 else "DUPLICATE"
    if not state.get("stopped_at"):
        set_state(state, "DELIVERY_UNKNOWN", "bounded exact-ID recovery found no delivery")
        stop(state, "DELIVERY_UNKNOWN: do not resend this Message ID")
    return False


def verify_new_conversation(
    state: dict[str, Any],
    state_path: Path,
    manual_url: str | None,
    pre_send_url: str | None,
) -> bool:
    url = pre_send_url
    if manual_url:
        set_state(state, "VERIFYING_CONVERSATION", "verify the already-open manual URL and blank page")
    else:
        set_state(state, "CREATING_CONVERSATION", "create a blank conversation without sending")
        before_new_count = state["external_command_count"]
        created = command(state, state_path, "new", ["chatgpt", "new", "-f", "json", "--window", "background"], state["parameters"]["command_wait_seconds"])
        state["new_command_called"] = state["external_command_count"] > before_new_count
        if created is None:
            return False
        created_rows = result_rows(created)
        state["new_command_return_code"] = created.get("returncode")
        state["new_command_timed_out"] = bool(created.get("timed_out"))
        state["new_command_result_classification"] = (
            "STATUS_ROWS_RETURNED" if created_rows
            else "TIMEOUT" if created.get("timed_out")
            else "NONZERO" if created.get("returncode") != 0
            else "EMPTY_OR_UNPARSEABLE_SUCCESS"
        )
        set_state(state, "VERIFYING_CONVERSATION", "verify URL changed and blank page has no messages")
        status = command(state, state_path, "status-new", ["chatgpt", "status", "-f", "json", "--window", "background"], state["parameters"]["command_wait_seconds"])
        if status is None:
            return False
        url = status_url(status)
        state["browser_navigation_occurred"] = bool(url and pre_send_url and url != pre_send_url)
    if not blank_new_url(url, state["pre_send_active_conversation_id"]):
        stop(state, "VERIFY_NEW_CONVERSATION_FAILED: still on an old /c/<id> page or URL is not a blank ChatGPT page")
        return False
    read_result = command(state, state_path, "read-new", ["chatgpt", "read", "-f", "json", "--window", "background"], state["parameters"]["command_wait_seconds"])
    if read_result is None:
        return False
    classification = classify_chatgpt_read_result(read_result)
    state["read_result"] = classification
    if classification == "NON_EMPTY":
        stop(state, "READ_NOT_EMPTY")
        return False
    if classification != "EMPTY":
        stop(state, "READ_UNPARSEABLE")
        return False
    state["blank_environment_verified"] = True
    state["verified_target_url"] = url
    state["created_conversation_id"] = None
    state["created_identity_status"] = "NOT_AVAILABLE_BEFORE_FIRST_WRITE"
    return True


def send_command(args: argparse.Namespace, payload_body: str | None = None) -> int:
    if args.prepare_new and (args.conversation or args.manual_new_url):
        raise ValueError("--prepare-new cannot be combined with --conversation or --manual-new-url")
    verified_continuation_state = getattr(args, "verified_continuation_state", None)
    if verified_continuation_state and (args.prepare_new or not args.conversation):
        raise ValueError(
            "--verified-continuation-state requires one explicit --conversation target"
        )
    required_values = {
        "WORK_ITEM_ID": args.work_item_id,
        "MESSAGE_ID": args.message_id,
        "MESSAGE_TYPE": args.message_type,
    }
    for name in (
        "conversation", "manual_new_url",
        "message_file", "state_file",
    ):
        value = getattr(args, name, None)
        if value is not None:
            required_values[name.upper()] = value
    if verified_continuation_state is not None:
        required_values["VERIFIED_CONTINUATION_STATE"] = verified_continuation_state
    unresolved = unresolved_required_values(required_values)
    if unresolved:
        report = assess_experiment_protocol(required_values, [])
        report.update({
            "operation": "SEND",
            "send_attempt_count": 0,
            "stop_reason": "REQUIRED_VALUE_UNRESOLVED",
            "test_result": "BLOCKED_BEFORE_EXECUTION",
        })
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 2
    state_path = Path(args.state_file) if args.state_file else default_state_path(args.work_item_id, args.message_id)
    receipt_path = write_receipt_path(args.work_item_id, args.message_id)
    if receipt_path.exists():
        raise ValueError("MESSAGE_ID already has a canonical write receipt; same-ID resend is forbidden")
    if state_path.exists():
        existing = read_json(state_path)
        if existing.get("message_id") != args.message_id:
            raise ValueError("existing state file belongs to another MESSAGE_ID")
        if existing.get("delivery_state") in NO_RESEND_STATES or existing.get("send_attempt_count", 0) >= 1:
            raise ValueError(f"MESSAGE_ID already has state {existing.get('delivery_state')}; same-ID resend is forbidden")
    state = new_state(args, state_path)
    state["write_receipt_path"] = str(receipt_path)
    body = payload_body if payload_body is not None else read_payload(args)
    payload = prepare_payload(args, body)
    payload_bytes = payload.encode("utf-8")
    state["payload_integrity"] = {
        "transport_method": "argv",
        "byte_length": len(payload_bytes),
        "character_length": len(payload),
        "line_count": len(payload.splitlines()),
        "sha256": hashlib.sha256(payload_bytes).hexdigest(),
        "has_work_item_id": has_exact_header(payload, "WORK_ITEM_ID", args.work_item_id),
        "has_message_id": has_exact_header(payload, "MESSAGE_ID", args.message_id),
        "has_end_sentinel": f"RR-PACKET-COMPLETE:{args.message_id}" in payload,
    }
    pre_rows: list[dict[str, Any]] = []
    if args.prepare_new:
        pre_rows = history(state, state_path)
    pre_status = command(state, state_path, "status-before-send", ["chatgpt", "status", "-f", "json", "--window", "background"], args.command_wait_seconds)
    pre_url = status_url(pre_status)
    state["pre_send_active_conversation_id"] = conversation_id_from_url(pre_url or "")
    if state["pre_send_active_conversation_id"]:
        record_identity_observation(
            state, "CURRENT_BROWSER", state["pre_send_active_conversation_id"],
            "PRE_SEND_STATUS", state["raw_outputs"][-1] if pre_status is not None else None,
        )
    state["pre_send_already_new"] = blank_new_url(pre_url, None)
    if args.manual_new_url and pre_url != args.manual_new_url:
        stop(state, "VERIFY_NEW_CONVERSATION_FAILED: current URL does not match manual blank URL")
        write_json(state_path, state)
        return output_state(state)
    if not args.prepare_new and not verified_continuation_state:
        pre_rows = history(state, state_path)
    state["pre_send_recent_conversation_ids"] = [identity for row in pre_rows if (identity := conversation_identity(row)[0])]
    write_json(state_path, state)
    if args.conversation:
        if verified_continuation_state:
            verified = verify_persisted_continuation_target(
                state, state_path, Path(verified_continuation_state),
                args.conversation,
            )
            if not verified:
                set_state(
                    state, "VERIFYING_CONVERSATION",
                    "persisted exact continuation target could not be verified read-only",
                )
                stop(
                    state,
                    "VERIFY_EXISTING_CONVERSATION_FAILED: persisted exact target is inaccessible or identity-unverified",
                )
                write_json(state_path, state)
                return output_state(state)
        elif (
            args.conversation not in state["pre_send_recent_conversation_ids"]
            and args.conversation != state["pre_send_active_conversation_id"]
        ):
            stop(state, "VERIFY_EXISTING_CONVERSATION_FAILED: explicit target was not observed in bounded pre-send evidence")
            write_json(state_path, state)
            return output_state(state)
        establish_identity(state, "TARGET", args.conversation, "EXPLICIT_SEND_ARGUMENT")
        state["verified_target_conversation_id"] = args.conversation
        target = ["--conversation", args.conversation]
    else:
        if not verify_new_conversation(state, state_path, args.manual_new_url, pre_url):
            write_json(state_path, state)
            return output_state(state)
        target = []
    if state["send_attempt_count"] >= state["parameters"]["max_send_attempts_per_message"]:
        stop(state, "EXPERIMENT_BUDGET_EXHAUSTED: MAX_SEND_ATTEMPTS_PER_MESSAGE")
        write_json(state_path, state)
        return output_state(state)
    set_state(state, "SENDING", "single OpenCLI send on the verified target or blank /new page")
    write_json(state_path, state)
    def mark_send_invoked() -> None:
        # Persist the one permitted write at the actual invocation boundary.
        # A process crash during send must still make a same-ID retry impossible.
        create_write_receipt(
            receipt_path, args.work_item_id, args.message_id, state_path,
        )
        state["send_attempted"] = True
        state["send_attempt_count"] = 1
        state["message_send_count"] = 1
        write_json(state_path, state)

    send_hard_timeout = min(
        float(args.command_wait_seconds) + ASK_HARD_TIMEOUT_GRACE_SECONDS,
        remaining_experiment_seconds(state),
    )
    if send_hard_timeout <= 0:
        stop(state, "EXPERIMENT_BUDGET_EXHAUSTED: SEND")
        write_json(state_path, state)
        return output_state(state)
    state["parameters"]["send_hard_timeout_seconds"] = round(send_hard_timeout, 3)
    result = command(
        state,
        state_path,
        "send",
        ["chatgpt", "send", payload, *target, "-f", "json", "--window", "background"],
        send_hard_timeout,
        before_invoke=mark_send_invoked,
    )
    if result is None:
        write_json(state_path, state)
        return output_state(state)
    returned_id, _ = ask_identity(result)
    state["send_return_code"] = result.get("returncode")
    state["send_error_code"] = cli_error_code(str(result.get("stderr") or ""))
    state["send_timed_out"] = bool(
        result.get("timed_out") or state["send_error_code"] == "TIMEOUT"
    )
    state["send_process_tree_terminated"] = result.get("process_tree_terminated", False)
    state["write_reported_conversation_id"] = returned_id
    record_identity_observation(
        state, "WRITE_REPORTED_CANDIDATE", returned_id, "SEND_RESULT",
        state["raw_outputs"][-1],
    )
    begin_post_send_verification(state)
    post_status = capture_post_send_status(state, state_path)
    if post_status is None:
        set_state(state, "DELIVERY_UNKNOWN", "post-send Browser identity could not be captured")
        stop(state, "DELIVERY_UNKNOWN: do not resend this Message ID", "IN_PROGRESS")
        write_json(state_path, state)
        return output_state(state)
    post_status_id = state.get("post_send_active_conversation_id")
    if (
        not post_status_id
        and state.get("target_binding_mode") == "NEW_SESSION_FIRST_WRITE"
        and result.get("returncode") == 0
        and not state.get("send_timed_out")
        and state.get("post_send_page_mode") in {"NEW", "ROOT"}
    ):
        post_status = wait_for_post_send_navigation(state, state_path)
        post_status_id = state.get("post_send_active_conversation_id")
        if not post_status_id:
            set_state(
                state, "DELIVERY_UNKNOWN",
                "bounded post-send navigation wait did not expose an exact Conversation identity",
            )
            stop(state, "DELIVERY_UNKNOWN: do not resend this Message ID", "IN_PROGRESS")
            write_json(state_path, state)
            return output_state(state)
    identity_conflict = bool(returned_id and post_status_id and returned_id != post_status_id)
    if identity_conflict:
        set_state(state, "DELIVERY_UNKNOWN", "send result identity conflicts with post-send Browser identity")
        stop(state, "DELIVERY_UNKNOWN: do not resend this Message ID", "IN_PROGRESS")
    elif not post_status_id:
        set_state(state, "DELIVERY_UNKNOWN", "post-send status did not expose an exact Conversation identity")
        if result.get("returncode") == 0 and not state.get("send_timed_out"):
            recover_delivery(
                state, state_path, returned_id, post_status,
                post_send_status_checked=True,
            )
        if (
            not state.get("stopped_at")
            and state.get("delivery_state") not in {"RESPONSE_PENDING", "RESPONSE_READY", "MISROUTED_DELIVERY"}
        ):
            stop(state, "DELIVERY_UNKNOWN: do not resend this Message ID", "IN_PROGRESS")
    else:
        read_result = command(
            state, state_path, "read-after-send",
            ["chatgpt", "read", "-f", "json", "--window", "background"],
            state["parameters"]["command_wait_seconds"],
        )
        batch = ResponseMessageBatch(
            conversation_id=post_status_id,
            messages=tuple(result_rows(read_result)),
            source_kind="POST_SEND_CURRENT_PAGE_READ",
            raw_output_path=state["raw_outputs"][-1] if read_result is not None else None,
        )
        if state.get("send_timed_out") or result.get("returncode") != 0:
            establish_identity(
                state, "RECOVERED", post_status_id,
                "POST_WRITE_UNCERTAIN_CURRENT_CANDIDATE",
                batch.raw_output_path,
            )
        if read_result is None or not establish_verified_delivery(state, batch):
            if (
                read_result is not None
                and state.get("delivery_marker_status") == "MISSING"
                and not identity_conflict
                and result.get("returncode") == 0
                and not state.get("send_timed_out")
            ):
                recover_delivery(
                    state, state_path, returned_id, post_status,
                    post_send_status_checked=True,
                )
            if (
                not state.get("stopped_at")
                and state.get("delivery_state") not in {"MISROUTED_DELIVERY", "RESPONSE_PENDING", "RESPONSE_READY"}
            ):
                set_state(state, "DELIVERY_UNKNOWN", "post-send exact marker was missing, duplicate, or ambiguous")
                stop(state, "DELIVERY_UNKNOWN: do not resend this Message ID", "IN_PROGRESS")
        else:
            accept_delivery(state, batch)
    write_json(state_path, state)
    return output_state(state)


def recover_command(args: argparse.Namespace) -> int:
    state_path = Path(args.state_file)
    state = ensure_identity_schema(read_json(state_path))
    if args.continue_pending:
        return continue_pending_response(
            state, state_path, allow_after_window_limit=bool(args.late_check)
        )
    if state.get("delivery_state") == "MISROUTED_DELIVERY":
        return output_state(state)
    if not recovery_budget_available(state, "manual"):
        stop(state, "EXPERIMENT_BUDGET_EXHAUSTED: MAX_MANUAL_RECOVERY_ATTEMPTS")
        write_json(state_path, state)
        return output_state(state)
    begin_operation(state, "MANUAL_RECOVER")
    restore_legacy_candidate_evidence(state)
    recover_delivery(
        state,
        state_path,
        state.get("candidate_conversation_id")
        or state.get("actual_delivery_conversation_id"),
        recovery_kind="manual",
    )
    write_json(state_path, state)
    return output_state(state)


def continue_pending_response(
    state: dict[str, Any], state_path: Path, *, allow_after_window_limit: bool = False,
) -> int:
    """Run one bounded exact-ID response window without sending or changing target."""
    state.setdefault("pending_response_continuation_count", 0)
    state.setdefault("pending_response_last_checked_at", None)
    state.setdefault("pending_response_last_result", None)
    state.setdefault("parameters", {}).setdefault(
        "max_pending_response_continuations", MAX_PENDING_RESPONSE_CONTINUATIONS
    )
    target = state.get("verified_target_conversation_id")
    allowed_delivery_states = {"RESPONSE_PENDING"}
    if allow_after_window_limit:
        allowed_delivery_states.add("BLOCKED_RESPONSE_TIMEOUT")
    if (
        state.get("delivery_state") not in allowed_delivery_states
        or state.get("response_identity_status") != "RESPONSE_PENDING"
        or not target
        or not state.get("work_item_id")
        or not state.get("message_id")
        or state.get("actual_delivery_conversation_id") != target
    ):
        raise ValueError(
            "pending response continuation requires confirmed RESPONSE_PENDING delivery, "
            "saved identity, and matching verified Conversation"
        )
    limit = state["parameters"]["max_pending_response_continuations"]
    if state["pending_response_continuation_count"] >= limit and not allow_after_window_limit:
        state["pending_response_last_result"] = "BLOCKED_RESPONSE_TIMEOUT"
        set_state(
            state, "BLOCKED_RESPONSE_TIMEOUT",
            "bounded Browser response windows exhausted without authoritative reply",
        )
        stop(
            state,
            "BLOCKED_RESPONSE_TIMEOUT: no authoritative Browser reply; local Review is forbidden",
            "STALLED",
        )
        write_json(state_path, state)
        return output_state(state)

    begin_operation(state, "PENDING_RESPONSE_CONTINUATION")
    if allow_after_window_limit:
        state["late_response_check_count"] = state.get("late_response_check_count", 0) + 1
    else:
        state["pending_response_continuation_count"] += 1
    state["pending_response_window_seconds"] = TOTAL_RESPONSE_WAIT_SECONDS
    write_json(state_path, state)
    result = command(
        state,
        state_path,
        "pending-response-detail",
        [
            "chatgpt", "detail", target, "--wait",
            "--timeout", str(TOTAL_RESPONSE_WAIT_SECONDS),
            "--stable", str(STABLE_SECONDS),
            "-f", "json", "--window", "background",
        ],
        TOTAL_RESPONSE_WAIT_SECONDS + ASK_HARD_TIMEOUT_GRACE_SECONDS,
    )
    result_available = bool(
        result is not None
        and not result.get("timed_out")
        and result.get("returncode") == 0
        and isinstance(parse_json(str(result.get("stdout") or "")), (dict, list))
    )
    batch = ResponseMessageBatch(
        conversation_id=target,
        messages=tuple(result_rows(result)),
        source_kind="PENDING_DETAIL_RESULT",
        raw_output_path=state["raw_outputs"][-1] if result is not None else None,
    )
    if result_available:
        accept_delivery(state, batch)
    else:
        state["response_identity_status"] = "RESPONSE_PENDING"
        state["official_response_eligible"] = False
        set_state(
            state, "RESPONSE_PENDING",
            "bounded exact-ID response window ended without a readable completed response",
        )
        stop(state, "RESPONSE_PENDING: Browser Review Authority remains pending", "IN_PROGRESS")
    identity_status = state["response_identity_status"]
    state["pending_response_last_identity_status"] = identity_status
    if identity_status == "RESPONSE_IDENTITY_VERIFIED":
        state["pending_response_last_result"] = "RESPONSE_READY"
    elif identity_status == "RESPONSE_PENDING":
        if allow_after_window_limit or state["pending_response_continuation_count"] >= limit:
            state["pending_response_last_result"] = "BLOCKED_RESPONSE_TIMEOUT"
            set_state(
                state, "BLOCKED_RESPONSE_TIMEOUT",
                "bounded Browser response windows exhausted without authoritative reply",
            )
            stop(
                state,
                "BLOCKED_RESPONSE_TIMEOUT: no authoritative Browser reply; local Review is forbidden",
                "STALLED",
            )
        else:
            state["pending_response_last_result"] = "RESPONSE_PENDING"
    else:
        state["pending_response_last_result"] = "RESPONSE_IDENTITY_REJECTED"
        state["response_identity_status"] = "RESPONSE_IDENTITY_REJECTED"
        set_state(state, "RESPONSE_IDENTITY_REJECTED", "stable Assistant response failed exact RR identity")
        stop(state, "RESPONSE_IDENTITY_REJECTED", "IN_PROGRESS")
    write_json(state_path, state)
    return output_state(state)


def output_state(state: dict[str, Any]) -> int:
    print(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if state["delivery_state"] == "RESPONSE_READY" else (1 if state["delivery_state"] == "FAILED" else 2)


def cleanup_command(args: argparse.Namespace) -> int:
    state_path = Path(args.state_file).resolve()
    state = read_json(state_path)
    allowed_root = (Path(tempfile.gettempdir()) / "research-review-lead").resolve()
    if allowed_root not in state_path.parents:
        raise ValueError("cleanup only removes records under the RR Lead system-temp directory")
    for raw in state.get("raw_outputs", []):
        raw_path = Path(raw).resolve()
        if allowed_root in raw_path.parents and raw_path.is_file():
            raw_path.unlink()
    state_path.unlink()
    print(json.dumps({"cleaned_state_file": str(state_path)}, indent=2))
    return 0


def _manual_export_state(args: argparse.Namespace, state_path: Path) -> dict[str, Any]:
    """Minimal manual-relay state that never implies an OpenCLI send path."""
    started = utc_now()
    return {
        "schema_version": 4, "work_item_id": args.work_item_id, "message_id": args.message_id,
        "operation": "MANUAL_EXPORT", "prepare_new": False,
        "round": args.round, "message_type": args.message_type,
        "expected_conversation_mode": "MANUAL_RELAY",
        "pre_send_active_conversation_id": None, "verified_target_conversation_id": None,
        "actual_delivery_conversation_id": None, "verified_target_url": None,
        "delivery_state": "NOT_SENT", "work_item_state": "IN_PROGRESS",
        "transport_state": "MANUAL_RELAY_REQUIRED",
        "send_attempted": False, "send_attempt_count": 0, "message_send_count": 0,
        "recovery_attempt_count": 0, "automatic_recovery_attempt_count": 0,
        "manual_recovery_attempt_count": 0, "detail_check_count": 0,
        "external_command_count": 0, "misroute_detected": False,
        "read_result": "NOT_RUN", "blank_environment_verified": False,
        "pre_send_already_new": False, "new_command_called": False,
        "browser_navigation_occurred": False,
        "official_response_eligible": False,
        "response_identity_status": "RESPONSE_PENDING",
        "response_source_conversation_id": None, "response_source_kind": None,
        "response_raw_output_path": None, "verified_rr_review": None,
        "started_at": started, "original_send_started_at": started,
        "current_operation": "MANUAL_EXPORT", "current_operation_started_at": started,
        "current_operation_external_command_count": 0,
        "manual_recover_started_at": None, "manual_recover_external_command_count": 0,
        "pending_response_continuation_count": 0, "late_response_check_count": 0,
        "pending_response_window_seconds": TOTAL_RESPONSE_WAIT_SECONDS,
        "pending_response_last_checked_at": None, "pending_response_last_result": None,
        "stopped_at": None, "stop_reason": None, "updated_at": utc_now(),
        "state_file": str(state_path), "raw_outputs": [], "transitions": [],
        "post_send_status_url": None, "post_send_active_conversation_id": None,
        "post_send_page_mode": "NOT_RUN", "post_send_history_called": False,
        "post_send_history_available": False, "post_send_recent_conversation_ids": [],
        "new_candidate_diff": [], "recovery_target_source": None,
        "recovery_target_conversation_id": None, "candidate_conversation_id": None,
        "candidate_conversation_source": None, "candidate_conversation_conflict": False,
        "candidate_conversation_conflicts": [],
        "last_observed_status_conversation_id": None,
        "manual_export_at": started, "exported_body_sha256": None, "exported_body_byte_length": None,
        "parameters": {
            "command_wait_seconds": COMMAND_WAIT_SECONDS,
            "max_send_attempts_per_message": MAX_SEND_ATTEMPTS_PER_MESSAGE,
            "max_recovery_attempts": MAX_RECOVERY_ATTEMPTS,
            "max_detail_checks": MAX_DETAIL_CHECKS,
            "max_external_commands": MAX_EXTERNAL_COMMANDS,
            "max_experiment_seconds": MAX_EXPERIMENT_SECONDS,
            "recent_candidate_limit": RECENT_CANDIDATE_LIMIT,
            "max_pending_response_continuations": MAX_PENDING_RESPONSE_CONTINUATIONS,
            "pending_response_wait_window_seconds": TOTAL_RESPONSE_WAIT_SECONDS,
        },
    }


def _export_payload_integrity(payload: str) -> dict[str, Any]:
    payload_bytes = payload.encode("utf-8")
    return {
        "byte_length": len(payload_bytes),
        "character_length": len(payload),
        "line_count": len(payload.splitlines()),
        "sha256": hashlib.sha256(payload_bytes).hexdigest(),
    }


def manual_export_command(args: argparse.Namespace) -> int:
    """Export the prepared final payload for a human to paste in the Browser.

    Never calls OpenCLI, never creates a conversation, never increments any send
    count, and derives the copyable body from the exact payload a send would use.
    """
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    required_values = {
        "WORK_ITEM_ID": args.work_item_id,
        "MESSAGE_ID": args.message_id,
        "MESSAGE_TYPE": args.message_type,
        "STATE_FILE": args.state_file,
    }
    for name, value in (("MESSAGE_FILE", args.message_file), ("ROUND", args.round)):
        if value is not None:
            required_values[name] = value
    unresolved = unresolved_required_values(required_values)
    if unresolved:
        report = assess_experiment_protocol(required_values, [])
        report.update({
            "operation": "MANUAL_EXPORT",
            "stop_reason": "REQUIRED_VALUE_UNRESOLVED",
            "test_result": "BLOCKED_BEFORE_EXECUTION",
        })
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 2
    body = read_payload(args)
    payload = prepare_payload(args, body)
    integrity = _export_payload_integrity(payload)
    state_path = Path(args.state_file)
    state = read_json(state_path) if state_path.exists() else _manual_export_state(args, state_path)
    receipt_path = write_receipt_path(args.work_item_id, args.message_id)
    if state.get("send_attempt_count", 0) >= 1 or receipt_path.exists():
        raise ValueError(
            "manual-export is forbidden after a Product write claim; use a newly authorized logical Message ID"
        )
    set_state(state, "MANUAL_RELAY_REQUIRED", "manual relay export prepared; user pastes into the Browser")
    state["work_item_state"] = "IN_PROGRESS"
    state.setdefault("send_attempted", False)
    state.setdefault("send_attempt_count", 0)
    state.setdefault("message_send_count", 0)
    state["transport_state"] = "MANUAL_RELAY_REQUIRED"
    state["manual_export_at"] = utc_now()
    state["exported_body_sha256"] = integrity["sha256"]
    state["exported_body_byte_length"] = integrity["byte_length"]
    state["payload_integrity"] = integrity
    write_json(state_path, state)
    conversation_required = getattr(args, "conversation_required", None) or "NEW"
    header = (
        "MANUAL_RELAY_EXPORT\n"
        f"WORK_ITEM_ID: {args.work_item_id}\n"
        f"MESSAGE_ID: {args.message_id}\n"
        f"MESSAGE_TYPE: {args.message_type}\n"
        f"ROUND: {args.round}\n"
        f"CONVERSATION_REQUIRED: {conversation_required}\n"
        f"BYTE_LENGTH: {integrity['byte_length']}\n"
        f"CHARACTER_LENGTH: {integrity['character_length']}\n"
        f"LINE_COUNT: {integrity['line_count']}\n"
        f"SHA256: {integrity['sha256']}\n"
        "WORK_ITEM_STATE: IN_PROGRESS\n"
        "TRANSPORT_STATE: MANUAL_RELAY_REQUIRED\n"
        "SEND_ATTEMPTED: false\n"
        "BEGIN_MESSAGE\n"
        f"{payload}\n"
        "END_MESSAGE"
    )
    print(header)
    return 2


def bootstrap_command(args: argparse.Namespace) -> int:
    """Create a real Browser RR Lead: assemble init + context, then one send."""
    body = bootstrap_body(args)
    return send_command(args, payload_body=body)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser(
        "prepare-new",
        help="A2.1: create and verify a blank conversation, persist state, and stop without sending",
    )
    prepare.add_argument("--runtime-dir", required=True)
    prepare.add_argument("--work-item-id", required=True)
    prepare.add_argument(
        "--require-existing-conversation",
        action="store_true",
        help="stop before new unless the initial status is an exact ChatGPT /c/<id> page",
    )
    prepare.add_argument("--command-wait-seconds", type=float, default=COMMAND_WAIT_SECONDS)
    prepare.add_argument("--max-external-commands", type=int, default=PREPARE_MAX_EXTERNAL_COMMANDS)
    prepare.add_argument("--max-experiment-seconds", type=float, default=MAX_EXPERIMENT_SECONDS)
    prepare.set_defaults(handler=prepare_new_command)
    send = sub.add_parser("send", help="CREATE_NEW_CONVERSATION -> VERIFY_NEW_CONVERSATION -> SEND_MESSAGE")
    send.add_argument("--work-item-id", required=True)
    send.add_argument("--message-id", required=True)
    send.add_argument("--round", required=True, type=int)
    send.add_argument("--message-type", required=True)
    send.add_argument("--conversation", help="explicit existing Conversation ID for a continuation")
    send.add_argument(
        "--verified-continuation-state",
        help="prior Product Transport state proving the exact continuation target",
    )
    send.add_argument(
        "--prepare-new", action="store_true",
        help="START_NEW_AND_SEND: create, verify, send once, and recover in one Wrapper call",
    )
    send.add_argument("--manual-new-url", help="current manually opened blank ChatGPT URL; must match status")
    send.add_argument("--message-file")
    send.add_argument("--state-file")
    send.add_argument("--command-wait-seconds", type=int, default=COMMAND_WAIT_SECONDS)
    send.add_argument("--max-recovery-attempts", type=int, default=MAX_RECOVERY_ATTEMPTS)
    send.add_argument("--max-detail-checks", type=int, default=MAX_DETAIL_CHECKS)
    send.add_argument("--max-external-commands", type=int, default=MAX_EXTERNAL_COMMANDS)
    send.add_argument("--max-experiment-seconds", type=int, default=MAX_EXPERIMENT_SECONDS)
    send.add_argument(
        "--max-post-send-navigation-wait-seconds", type=float,
        default=MAX_POST_SEND_NAVIGATION_WAIT_SECONDS,
    )
    send.add_argument(
        "--max-navigation-status-checks", type=int,
        default=MAX_NAVIGATION_STATUS_CHECKS,
    )
    send.add_argument(
        "--post-send-navigation-poll-interval-seconds", type=float,
        default=POST_SEND_NAVIGATION_POLL_INTERVAL_SECONDS,
    )
    send.add_argument("--recent-candidate-limit", type=int, default=RECENT_CANDIDATE_LIMIT)
    send.set_defaults(handler=send_command)
    recover = sub.add_parser("recover", help="bounded delivery recovery or pending-response continuation without sending")
    recover.add_argument("--state-file", required=True)
    recover.add_argument(
        "--continue-pending",
        action="store_true",
        help="read one saved RESPONSE_PENDING Conversation without ask, send, or new",
    )
    recover.add_argument(
        "--late-check", action="store_true",
        help="perform one explicit read-only check after automatic response windows stalled",
    )
    recover.set_defaults(handler=recover_command)
    cleanup = sub.add_parser("cleanup")
    cleanup.add_argument("--state-file", required=True)
    cleanup.set_defaults(handler=cleanup_command)
    bootstrap = sub.add_parser(
        "bootstrap",
        help="deterministically create a real Browser RR Lead by assembling init + context",
    )
    bootstrap.add_argument("--work-item-id", required=True)
    bootstrap.add_argument("--message-id", required=True)
    bootstrap.add_argument("--round", type=int, default=0)
    bootstrap.add_argument("--message-type", default="CONTEXT_PACKET")
    bootstrap.add_argument("--init-file", required=True)
    bootstrap.add_argument("--context-file", required=True)
    bootstrap.add_argument(
        "--prepare-new", action="store_true",
        help="START_NEW_AND_SEND: create, verify, send once, and recover in one Wrapper call",
    )
    bootstrap.add_argument("--conversation", help="explicit existing Conversation ID for a continuation")
    bootstrap.add_argument("--verified-continuation-state")
    bootstrap.add_argument("--manual-new-url", help="current manually opened blank ChatGPT URL; must match status")
    bootstrap.add_argument("--state-file")
    bootstrap.add_argument("--command-wait-seconds", type=int, default=COMMAND_WAIT_SECONDS)
    bootstrap.add_argument("--max-recovery-attempts", type=int, default=MAX_RECOVERY_ATTEMPTS)
    bootstrap.add_argument("--max-detail-checks", type=int, default=MAX_DETAIL_CHECKS)
    bootstrap.add_argument("--max-external-commands", type=int, default=MAX_EXTERNAL_COMMANDS)
    bootstrap.add_argument("--max-experiment-seconds", type=int, default=MAX_EXPERIMENT_SECONDS)
    bootstrap.add_argument(
        "--max-post-send-navigation-wait-seconds", type=float,
        default=MAX_POST_SEND_NAVIGATION_WAIT_SECONDS,
    )
    bootstrap.add_argument(
        "--max-navigation-status-checks", type=int,
        default=MAX_NAVIGATION_STATUS_CHECKS,
    )
    bootstrap.add_argument(
        "--post-send-navigation-poll-interval-seconds", type=float,
        default=POST_SEND_NAVIGATION_POLL_INTERVAL_SECONDS,
    )
    bootstrap.add_argument("--recent-candidate-limit", type=int, default=RECENT_CANDIDATE_LIMIT)
    bootstrap.set_defaults(handler=bootstrap_command)
    manual_export = sub.add_parser(
        "manual-export",
        help="export the prepared final payload for a human to paste into the Browser RR Lead conversation",
    )
    manual_export.add_argument("--work-item-id", required=True)
    manual_export.add_argument("--message-id", required=True)
    manual_export.add_argument("--round", required=True, type=int)
    manual_export.add_argument("--message-type", required=True)
    manual_export.add_argument("--conversation-required", default="NEW")
    manual_export.add_argument("--message-file")
    manual_export.add_argument("--state-file", required=True)
    manual_export.set_defaults(handler=manual_export_command)
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        return int(args.handler(args))
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
