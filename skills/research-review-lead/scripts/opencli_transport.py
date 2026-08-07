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


def find_opencli() -> list[str]:
    test_executable = os.environ.get("OPENCLI_TRANSPORT_EXECUTABLE")
    if test_executable:
        return [sys.executable, test_executable]
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


def operation_elapsed_seconds(state: dict[str, Any]) -> float:
    started_at = state.get("current_operation_started_at") or state["started_at"]
    started = datetime.fromisoformat(started_at)
    return max(0.0, (datetime.now(timezone.utc) - started).total_seconds())


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
    if marker(args.message_id) in body:
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
        "schema_version": 4, "work_item_id": args.work_item_id, "message_id": args.message_id,
        "operation": "START_NEW_AND_SEND" if args.prepare_new else "SEND",
        "prepare_new": bool(args.prepare_new),
        "round": args.round, "message_type": args.message_type,
        "expected_conversation_mode": "EXISTING" if args.conversation else "NEW",
        "pre_send_active_conversation_id": None, "verified_target_conversation_id": args.conversation,
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
        "parameters": {
            "command_wait_seconds": args.command_wait_seconds,
            "max_send_attempts_per_message": MAX_SEND_ATTEMPTS_PER_MESSAGE,
            "max_recovery_attempts": args.max_recovery_attempts,
            "max_detail_checks": args.max_detail_checks,
            "max_external_commands": args.max_external_commands,
            "max_experiment_seconds": args.max_experiment_seconds,
            "recent_candidate_limit": args.recent_candidate_limit,
            "max_pending_response_continuations": MAX_PENDING_RESPONSE_CONTINUATIONS,
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


def mark_misroute(state: dict[str, Any], identity: str, raw_path: str | None) -> None:
    state["actual_delivery_conversation_id"] = identity
    state["misroute_detected"] = True
    state["official_response_eligible"] = False
    state["misroute_evidence"] = {"conversation_id": identity, "raw_path": raw_path,
                                  "matched_work_item_id": state["work_item_id"], "matched_message_id": state["message_id"]}
    set_state(state, "MISROUTED_DELIVERY", "exact Work Item ID and Message ID found in a pre-send conversation")
    stop(state, "MISROUTED_DELIVERY: repair new-conversation creation before retrying")


def pre_send_ids(state: dict[str, Any]) -> set[str]:
    identities = set(state.get("pre_send_recent_conversation_ids", []))
    if state.get("pre_send_active_conversation_id"):
        identities.add(state["pre_send_active_conversation_id"])
    return identities


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
    current_url = status_url(status)
    current_id = conversation_id_from_url(current_url or "")
    state["last_observed_status_conversation_id"] = current_id
    if current_url:
        state["post_send_status_url"] = current_url
    if current_id:
        state["post_send_active_conversation_id"] = current_id
    observe_candidate(state, current_id, "POST_SEND_STATUS")
    state["post_send_page_mode"] = page_mode(current_url)
    return status


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
            set_state(
                state,
                "MANUAL_RELAY_REQUIRED",
                "automatic recovery budget exhausted; use manual-export to relay",
            )
            state["work_item_state"] = "IN_PROGRESS"
            state["send_attempted"] = False
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

    add_candidate(
        state.get("candidate_conversation_id"),
        state.get("candidate_conversation_source") or "PERSISTED_CANDIDATE",
    )
    add_candidate(returned_identity, "ASK_REPORTED_CONVERSATION_ID")
    add_candidate(current_id, "POST_SEND_STATUS")
    if len(new_ids) == 1:
        add_candidate(new_ids[0], "POST_SEND_HISTORY_NEW_CANDIDATE_DIFF")
    elif len(new_ids) > 1 and not candidates:
        state["recovery_target_source"] = "AMBIGUOUS_NEW_CANDIDATE_DIFF"
    if candidates:
        identity, source = candidates[0]
        observe_candidate(state, identity, source)
        state["recovery_target_source"] = source
        state["recovery_target_conversation_id"] = identity
        response_batch = detail(state, state_path, identity)
        messages = list(response_batch.messages) if response_batch else []
        delivered, response_exists, ready = inspect_messages(messages, state["work_item_id"], state["message_id"])
        if delivered:
            if state.get("expected_conversation_mode") == "NEW" and identity in baseline:
                mark_misroute(
                    state, identity,
                    response_batch.raw_output_path if response_batch else None,
                )
            else:
                establish_verified_target(state, identity)
                if response_batch is not None:
                    accept_delivery(state, response_batch)
            return True
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
        if not result_rows(created):
            stop(state, "CREATE_NEW_CONVERSATION_UNVERIFIED")
            return False
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
    return True


def send_command(args: argparse.Namespace, payload_body: str | None = None) -> int:
    if args.prepare_new and (args.conversation or args.manual_new_url):
        raise ValueError("--prepare-new cannot be combined with --conversation or --manual-new-url")
    required_values = {
        "WORK_ITEM_ID": args.work_item_id,
        "MESSAGE_ID": args.message_id,
        "MESSAGE_TYPE": args.message_type,
    }
    for name in (
        "conversation", "manual_new_url", "message_file", "state_file",
    ):
        value = getattr(args, name, None)
        if value is not None:
            required_values[name.upper()] = value
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
    if state_path.exists():
        existing = read_json(state_path)
        if existing.get("message_id") != args.message_id:
            raise ValueError("existing state file belongs to another MESSAGE_ID")
        if existing.get("delivery_state") in NO_RESEND_STATES or existing.get("send_attempt_count", 0) >= 1:
            raise ValueError(f"MESSAGE_ID already has state {existing.get('delivery_state')}; same-ID resend is forbidden")
    state = new_state(args, state_path)
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
    state["pre_send_already_new"] = blank_new_url(pre_url, None)
    if args.manual_new_url and pre_url != args.manual_new_url:
        stop(state, "VERIFY_NEW_CONVERSATION_FAILED: current URL does not match manual blank URL")
        write_json(state_path, state)
        return output_state(state)
    if not args.prepare_new:
        pre_rows = history(state, state_path)
    state["pre_send_recent_conversation_ids"] = [identity for row in pre_rows if (identity := conversation_identity(row)[0])]
    write_json(state_path, state)
    if args.conversation:
        if args.conversation not in state["pre_send_recent_conversation_ids"] and args.conversation != state["pre_send_active_conversation_id"]:
            stop(state, "VERIFY_EXISTING_CONVERSATION_FAILED: explicit target was not observed in bounded pre-send evidence")
            write_json(state_path, state)
            return output_state(state)
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
    set_state(state, "SENDING", "single ask on verified target")
    write_json(state_path, state)
    def mark_send_invoked() -> None:
        # Persist the one permitted write at the actual invocation boundary.
        # A process crash during ask must still make a same-ID retry impossible.
        state["send_attempted"] = True
        state["send_attempt_count"] = 1
        state["message_send_count"] = 1
        write_json(state_path, state)

    recovery_reserve = min(
        float(args.command_wait_seconds),
        float(args.max_experiment_seconds) / 2,
    )
    ask_hard_timeout = min(
        float(args.command_wait_seconds) + ASK_HARD_TIMEOUT_GRACE_SECONDS,
        remaining_experiment_seconds(state) - recovery_reserve,
    )
    if ask_hard_timeout <= 0:
        stop(state, "EXPERIMENT_BUDGET_EXHAUSTED: ASK_RECOVERY_RESERVE")
        write_json(state_path, state)
        return output_state(state)
    state["parameters"]["ask_hard_timeout_seconds"] = round(ask_hard_timeout, 3)
    state["parameters"]["recovery_budget_reserve_seconds"] = recovery_reserve
    result = command(
        state,
        state_path,
        "ask",
        ["chatgpt", "ask", payload, *target, "--timeout", str(args.command_wait_seconds), "-f", "json", "--window", "background"],
        ask_hard_timeout,
        before_invoke=mark_send_invoked,
    )
    if result is None:
        write_json(state_path, state)
        return output_state(state)
    returned_id, returned_url = ask_identity(result)
    state["ask_return_code"] = result.get("returncode")
    state["ask_error_code"] = cli_error_code(str(result.get("stderr") or ""))
    state["ask_timed_out"] = bool(
        result.get("timed_out") or state["ask_error_code"] == "TIMEOUT"
    )
    state["ask_process_tree_terminated"] = result.get("process_tree_terminated", False)
    state["ask_reported_conversation_id"] = returned_id
    state["ask_reported_url"] = returned_url
    state["ask_delivery_classification"] = classify_ask_delivery(result, returned_id)
    ask_raw_path = state["raw_outputs"][-1]
    post_status = capture_post_send_status(state, state_path) if args.prepare_new else None
    if args.prepare_new and post_status is None:
        write_json(state_path, state)
        return output_state(state)
    post_status_id = state.get("post_send_active_conversation_id")
    identity_conflict = bool(returned_id and post_status_id and returned_id != post_status_id)
    if state["ask_timed_out"]:
        set_state(state, "DELIVERY_UNKNOWN", "ask timed out; same Message ID resend is forbidden")
        stop(state, "ASK_TIMEOUT: recover with the persisted state", "IN_PROGRESS")
    elif result["returncode"] != 0:
        set_state(state, "DELIVERY_UNKNOWN", "ask timed out or returned nonzero; one bounded recovery only")
        recover_delivery(
            state, state_path, returned_id, post_status,
            post_send_status_checked=args.prepare_new,
        )
    elif returned_id and returned_id in pre_send_ids(state) and not args.conversation:
        mark_misroute(state, returned_id, ask_raw_path)
    elif identity_conflict:
        set_state(state, "DELIVERY_UNKNOWN", "ask identity conflicts with post-send status")
        recover_delivery(
            state, state_path, returned_id, post_status,
            post_send_status_checked=True,
        )
    elif returned_id:
        state["actual_delivery_conversation_id"] = returned_id
        establish_verified_target(state, returned_id)
        response_batch = response_batch_from_ask(result, payload, ask_raw_path)
        if response_batch:
            accept_delivery(state, response_batch)
        else:
            state["response_identity_status"] = "RESPONSE_PENDING"
            state["official_response_eligible"] = False
            set_state(state, "DELIVERED", "ask returned verified new conversation identity without a response")
            stop(state, "BOUNDED_WAIT_COMPLETE", "IN_PROGRESS")
    else:
        set_state(state, "DELIVERY_UNKNOWN", "ask returned without conversation identity")
        recover_delivery(
            state, state_path, post_send_status=post_status,
            post_send_status_checked=args.prepare_new,
        )
    write_json(state_path, state)
    return output_state(state)


def recover_command(args: argparse.Namespace) -> int:
    state_path = Path(args.state_file)
    state = read_json(state_path)
    if args.continue_pending:
        return continue_pending_response(state, state_path)
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


def continue_pending_response(state: dict[str, Any], state_path: Path) -> int:
    """Read one already-delivered pending response without sending or navigating elsewhere."""
    state.setdefault("pending_response_continuation_count", 0)
    state.setdefault("pending_response_last_checked_at", None)
    state.setdefault("pending_response_last_result", None)
    state.setdefault("parameters", {}).setdefault(
        "max_pending_response_continuations", MAX_PENDING_RESPONSE_CONTINUATIONS
    )
    target = state.get("verified_target_conversation_id")
    if (
        state.get("delivery_state") != "RESPONSE_PENDING"
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
    if state["pending_response_continuation_count"] >= limit:
        state["pending_response_last_result"] = "BLOCKED_RESPONSE_TIMEOUT"
        set_state(state, "BLOCKED_RESPONSE_TIMEOUT", "pending response continuation limit exhausted")
        stop(state, "BLOCKED_RESPONSE_TIMEOUT")
        write_json(state_path, state)
        return output_state(state)

    begin_operation(state, "PENDING_RESPONSE_CONTINUATION")
    state["pending_response_continuation_count"] += 1
    write_json(state_path, state)
    result = command(
        state,
        state_path,
        "pending-response-detail",
        ["chatgpt", "detail", target, "-f", "json", "--window", "background"],
        state["parameters"]["command_wait_seconds"],
    )
    batch = ResponseMessageBatch(
        conversation_id=target,
        messages=tuple(result_rows(result)),
        source_kind="PENDING_DETAIL_RESULT",
        raw_output_path=state["raw_outputs"][-1] if result is not None else None,
    )
    stable_assistant_found = any(stable_assistant_text(message) for message in batch.messages)
    if not stable_assistant_found:
        status = command(
            state,
            state_path,
            "pending-response-status",
            ["chatgpt", "status", "-f", "json", "--window", "background"],
            state["parameters"]["command_wait_seconds"],
        )
        current_id = conversation_id_from_url(status_url(status) or "")
        if current_id != target:
            state["pending_response_last_identity_status"] = "RESPONSE_SOURCE_CONVERSATION_MISMATCH"
            state["response_identity_status"] = "RESPONSE_IDENTITY_REJECTED"
            state["official_response_eligible"] = False
            state["pending_response_last_result"] = "RESPONSE_IDENTITY_REJECTED"
            set_state(state, "RESPONSE_IDENTITY_REJECTED", "pending read source did not match saved Conversation")
            stop(state, "RESPONSE_IDENTITY_REJECTED", "IN_PROGRESS")
            write_json(state_path, state)
            return output_state(state)
        read_result = command(
            state,
            state_path,
            "pending-response-read",
            ["chatgpt", "read", "-f", "json", "--window", "background"],
            state["parameters"]["command_wait_seconds"],
        )
        batch = ResponseMessageBatch(
            conversation_id=target,
            messages=tuple(result_rows(read_result)),
            source_kind="PENDING_READ_RESULT",
            raw_output_path=state["raw_outputs"][-1] if read_result is not None else None,
        )

    accept_delivery(state, batch)
    identity_status = state["response_identity_status"]
    state["pending_response_last_identity_status"] = identity_status
    if identity_status == "RESPONSE_IDENTITY_VERIFIED":
        state["pending_response_last_result"] = "RESPONSE_READY"
    elif identity_status == "RESPONSE_PENDING":
        if state["pending_response_continuation_count"] >= limit:
            state["pending_response_last_result"] = "BLOCKED_RESPONSE_TIMEOUT"
            set_state(state, "BLOCKED_RESPONSE_TIMEOUT", "pending response continuation limit exhausted")
            stop(state, "BLOCKED_RESPONSE_TIMEOUT")
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
        "pending_response_continuation_count": 0,
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
    set_state(state, "MANUAL_RELAY_REQUIRED", "manual relay export prepared; user pastes into the Browser")
    state["work_item_state"] = "IN_PROGRESS"
    state["send_attempted"] = False
    state["send_attempt_count"] = 0
    state["message_send_count"] = 0
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
    send.add_argument("--recent-candidate-limit", type=int, default=RECENT_CANDIDATE_LIMIT)
    send.set_defaults(handler=send_command)
    recover = sub.add_parser("recover", help="bounded delivery recovery or pending-response continuation without sending")
    recover.add_argument("--state-file", required=True)
    recover.add_argument(
        "--continue-pending",
        action="store_true",
        help="read one saved RESPONSE_PENDING Conversation without ask, send, or new",
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
    bootstrap.add_argument("--manual-new-url", help="current manually opened blank ChatGPT URL; must match status")
    bootstrap.add_argument("--state-file")
    bootstrap.add_argument("--command-wait-seconds", type=int, default=COMMAND_WAIT_SECONDS)
    bootstrap.add_argument("--max-recovery-attempts", type=int, default=MAX_RECOVERY_ATTEMPTS)
    bootstrap.add_argument("--max-detail-checks", type=int, default=MAX_DETAIL_CHECKS)
    bootstrap.add_argument("--max-external-commands", type=int, default=MAX_EXTERNAL_COMMANDS)
    bootstrap.add_argument("--max-experiment-seconds", type=int, default=MAX_EXPERIMENT_SECONDS)
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
