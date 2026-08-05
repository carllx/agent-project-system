#!/usr/bin/env python3
"""Bounded OpenCLI transport for the RR Lead loop.

New-conversation delivery is deliberately split into create, verify, and send.
The wrapper never sends a MESSAGE_ID more than once and never treats a message
found in a pre-existing conversation as a successful RR Lead delivery.
"""

from __future__ import annotations

import argparse
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
from typing import Any, Callable
from urllib.parse import urlparse


PROCESS_MONOTONIC_STARTED = time.monotonic()
PROCESS_STARTED_AT = datetime.now(timezone.utc).isoformat(timespec="seconds")
COMMAND_WAIT_SECONDS = 15
POLL_INTERVAL_SECONDS = 5
TOTAL_RESPONSE_WAIT_SECONDS = 30
MAX_SEND_ATTEMPTS_PER_MESSAGE = 1
MAX_RECOVERY_ATTEMPTS = 1
MAX_DETAIL_CHECKS = 1
MAX_EXTERNAL_COMMANDS = 9
MAX_EXPERIMENT_SECONDS = 60
PREPARE_MAX_SEND_ATTEMPTS = 0
PREPARE_MAX_RECOVERY_ATTEMPTS = 0
PREPARE_MAX_DETAIL_CHECKS = 0
PREPARE_MAX_EXTERNAL_COMMANDS = 4
RECENT_CANDIDATE_LIMIT = 3
STABLE_SECONDS = 3
MAX_IDLE_WAIT_SECONDS = 0
MAX_SCHEDULE_CALLS = 0
MAX_POLL_ATTEMPTS = 0
MAX_BACKGROUND_RESULT_CHECKS = 1
MAX_BACKGROUND_WAIT_SECONDS = 15

EXPERIMENT_ACTION_TYPES = {
    "SHELL_COMMAND",
    "SCHEDULE",
    "SLEEP",
    "TIMER",
    "POLL",
    "FILE_SEARCH",
    "SOURCE_SEARCH",
    "LOG_SEARCH",
    "BACKGROUND_RESULT_CHECK",
}
ASYNC_INCOMPLETE_STATES = {
    "RUNNING",
    "PENDING",
    "PROCESS_STILL_ACTIVE",
    "JOB_ID_WITH_INCOMPLETE_RESULT",
}
STANDING_WAIT_PATTERNS = (
    "standing by",
    "waiting for timer",
    "i will report later",
    "等待下一次状态检测",
)

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
    "FAILED",
}
NO_RESEND_STATES = DELIVERY_STATES - {"NOT_SENT"}


def unresolved_required_values(required_values: dict[str, Any]) -> list[str]:
    """Return required field names whose values are absent or placeholders."""
    unresolved: list[str] = []
    for name, value in required_values.items():
        if value is None:
            unresolved.append(name)
            continue
        text = str(value).strip()
        lowered = text.lower()
        if (
            not text
            or lowered in {"null", "todo", "tbd", "placeholder"}
            or re.search(r"<[^>]*>", text)
            or "请在这里" in text
            or "example.com" in lowered
        ):
            unresolved.append(name)
    return unresolved


def assess_experiment_protocol(
    required_values: dict[str, Any],
    events: list[dict[str, Any]],
    *,
    max_external_commands: int = 1,
    polling_authorized: bool = False,
    max_idle_wait_seconds: float = MAX_IDLE_WAIT_SECONDS,
    max_schedule_calls: int = MAX_SCHEDULE_CALLS,
    max_poll_attempts: int = MAX_POLL_ATTEMPTS,
    max_background_result_checks: int = MAX_BACKGROUND_RESULT_CHECKS,
    max_background_wait_seconds: float = MAX_BACKGROUND_WAIT_SECONDS,
    final_text: str = "",
) -> dict[str, Any]:
    """Audit a synthetic experiment trace without executing external commands."""
    unresolved = unresolved_required_values(required_values)
    counts = {action: 0 for action in EXPERIMENT_ACTION_TYPES}
    failure_types: list[str] = []
    idle_wait_seconds = 0.0
    synchronous_command_completed = False
    background_state: str | None = None
    background_process_handle: str | None = None
    supported_result_method: str | None = None
    background_wait_seconds = 0.0
    completion_mode = "NONE"
    command_completed = False
    result_available_index: int | None = None
    schedules_proven_before_result = 0
    schedule_initiators: set[str] = set()

    for index, event in enumerate(events):
        action = str(event.get("action", "")).upper()
        if action in counts:
            counts[action] += 1
        seconds = event.get("seconds", 0)
        if action in {"SCHEDULE", "SLEEP", "TIMER"}:
            try:
                idle_wait_seconds += max(float(seconds), 0.0)
            except (TypeError, ValueError):
                failure_types.append("INVALID_WAIT_DURATION")

        if action == "TOOL_RESULT":
            state = str(event.get("status", "")).upper()
            background_state = state if state in ASYNC_INCOMPLETE_STATES else None
            handle = event.get("process_handle", event.get("job_id"))
            background_process_handle = str(handle).strip() if handle is not None else None
            if not background_process_handle:
                background_process_handle = None
            method = event.get("result_method")
            supported_result_method = str(method).strip() if method is not None else None
            if not supported_result_method:
                supported_result_method = None

        if action == "SHELL_COMMAND":
            result = event.get("result")
            if isinstance(result, dict) and {"exit_code", "stdout", "stderr"} <= result.keys():
                synchronous_command_completed = True
                result_available_index = index
                command_completed = True
                completion_mode = "SYNCHRONOUS_COMPLETION"
                background_state = None
                background_process_handle = None
                supported_result_method = None

        if action == "BACKGROUND_RESULT_CHECK":
            seconds = event.get("seconds", 0)
            try:
                background_wait_seconds += max(float(seconds), 0.0)
            except (TypeError, ValueError):
                failure_types.append("INVALID_WAIT_DURATION")
            check_handle = event.get("process_handle", event.get("job_id"))
            check_handle = str(check_handle).strip() if check_handle is not None else None
            result = event.get("result")
            check_allowed = (
                polling_authorized
                and background_state in ASYNC_INCOMPLETE_STATES
                and background_process_handle is not None
                and check_handle == background_process_handle
                and supported_result_method is not None
                and counts["BACKGROUND_RESULT_CHECK"] <= max_background_result_checks
                and background_wait_seconds <= max_background_wait_seconds
            )
            if not check_allowed:
                failure_types.append("UNBOUND_OR_UNSUPPORTED_BACKGROUND_WAIT")
            elif isinstance(result, dict) and {"exit_code", "stdout", "stderr"} <= result.keys():
                command_completed = True
                completion_mode = "BACKGROUND_PROCESS_COMPLETION"
                result_available_index = index
                background_state = None

        if action == "POLL":
            failure_types.append("UNBOUND_OR_UNSUPPORTED_BACKGROUND_WAIT")

        if action in {"SCHEDULE", "SLEEP", "TIMER"}:
            if action == "SCHEDULE" and event.get("completed_before_command_result") is True:
                schedules_proven_before_result += 1
            if action == "SCHEDULE":
                initiator = str(event.get("initiated_by", "UNKNOWN")).upper()
                if initiator not in {
                    "MODEL_INITIATED", "PLATFORM_REQUIRED", "PLATFORM_AUTO_INSERTED"
                }:
                    initiator = "UNKNOWN"
                schedule_initiators.add(initiator)
            if "UNAUTHORIZED_IDLE_WAIT" not in failure_types:
                failure_types.append("UNAUTHORIZED_IDLE_WAIT")

    if unresolved and events:
        failure_types.append("UNRESOLVED_PLACEHOLDER_EXECUTION")
    if counts["SHELL_COMMAND"] > max_external_commands:
        failure_types.append("EXTERNAL_COMMAND_BUDGET_EXCEEDED")
    if counts["SCHEDULE"] > max_schedule_calls:
        if "UNAUTHORIZED_IDLE_WAIT" not in failure_types:
            failure_types.append("UNAUTHORIZED_IDLE_WAIT")
    if idle_wait_seconds > max_idle_wait_seconds:
        if "UNAUTHORIZED_IDLE_WAIT" not in failure_types:
            failure_types.append("UNAUTHORIZED_IDLE_WAIT")
    if counts["BACKGROUND_RESULT_CHECK"] > max_background_result_checks:
        failure_types.append("BACKGROUND_RESULT_CHECK_BUDGET_EXCEEDED")
    if background_wait_seconds > max_background_wait_seconds:
        failure_types.append("BACKGROUND_WAIT_BUDGET_EXCEEDED")
    if max_external_commands == 1 and result_available_index is not None and result_available_index != len(events) - 1:
        if "UNAUTHORIZED_IDLE_WAIT" not in failure_types:
            failure_types.append("UNAUTHORIZED_IDLE_WAIT")
    if any(pattern in final_text.lower() for pattern in STANDING_WAIT_PATTERNS):
        failure_types.append("STANDING_WAIT_OUTPUT")

    schedule_before_result_proven = (
        counts["SCHEDULE"] > 0
        and schedules_proven_before_result == counts["SCHEDULE"]
    )
    terminated_immediately = result_available_index is not None and result_available_index == len(events) - 1
    if counts["SCHEDULE"] and not schedule_before_result_proven:
        terminated_immediately = False
    if not command_completed and counts["SCHEDULE"]:
        completion_mode = "IDLE_TIMER_WAIT"
    protocol_result = "PASS"
    if unresolved:
        protocol_result = "BLOCKED_BEFORE_EXECUTION"
    if failure_types:
        protocol_result = "TEST_PROTOCOL_VIOLATION"
    agent_schedule_call_count = counts["SCHEDULE"]
    report = {
        "PROTOCOL_RESULT": protocol_result,
        "TEST_RESULT": protocol_result,
        "TEST_PROTOCOL_VIOLATION": bool(failure_types),
        "FAILURE_TYPES": list(dict.fromkeys(failure_types)),
        "PLACEHOLDER_VALIDATION_PERFORMED": True,
        "UNRESOLVED_PLACEHOLDERS": unresolved,
        "EXTERNAL_COMMAND_COUNT": counts["SHELL_COMMAND"],
        "EXPERIMENT_ACTION_COUNT": sum(counts.values()),
        "ACTION_COUNTS": counts,
        "WRAPPER_SCHEDULE_CALL_COUNT": 0,
        "AGENT_SCHEDULE_CALL_COUNT": agent_schedule_call_count,
        "TOTAL_SCHEDULE_CALL_COUNT": agent_schedule_call_count,
        # Compatibility alias. It is the verified total, never the Wrapper-only count.
        "SCHEDULE_CALL_COUNT": agent_schedule_call_count,
        "VISIBLE_SCHEDULE_TOOL_CALL_EXISTS": agent_schedule_call_count > 0,
        "AGENT_TOOL_TRACE_VERIFICATION": "VERIFIED",
        "AGENT_BOUND_RESULT_RETRIEVAL_COUNT": counts["BACKGROUND_RESULT_CHECK"],
        "WHO_INITIATED_SCHEDULE": (
            next(iter(schedule_initiators)) if len(schedule_initiators) == 1 else
            "NONE" if not schedule_initiators else "UNKNOWN"
        ),
        "IDLE_WAIT_SECONDS": idle_wait_seconds,
        "POLL_ATTEMPT_COUNT": counts["POLL"],
        "BACKGROUND_RESULT_CHECK_COUNT": counts["BACKGROUND_RESULT_CHECK"],
        "BACKGROUND_WAIT_SECONDS": background_wait_seconds,
        "BACKGROUND_PROCESS_HANDLE_SUPPORT": background_process_handle is not None,
        "SUPPORTED_WAIT_OR_RESULT_METHOD": supported_result_method or "NONE",
        "COMMAND_COMPLETED": command_completed,
        "COMPLETION_MODE": completion_mode,
        "SYNCHRONOUS_COMMAND_COMPLETED": synchronous_command_completed,
        "TERMINATED_IMMEDIATELY_AFTER_RESULT": terminated_immediately,
        "SCHEDULE_COMPLETED_BEFORE_COMMAND_RESULT_PROVEN": schedule_before_result_proven,
        "EXPERIMENT_ACCEPTANCE": "NOT_MET" if failure_types else "MET",
    }
    return validate_experiment_report(report)


def validate_experiment_report(report: dict[str, Any]) -> dict[str, Any]:
    """Fail a report whose completion, waiting, or result claims conflict."""
    validated = dict(report)
    failures: list[str] = []
    required_trace_fields = {
        "WRAPPER_SCHEDULE_CALL_COUNT", "AGENT_SCHEDULE_CALL_COUNT",
        "TOTAL_SCHEDULE_CALL_COUNT", "AGENT_TOOL_TRACE_VERIFICATION",
        "AGENT_BOUND_RESULT_RETRIEVAL_COUNT", "EXPERIMENT_ACCEPTANCE",
    }
    for field in sorted(required_trace_fields - validated.keys()):
        failures.append(f"MISSING_REQUIRED_REPORT_FIELD:{field}")
    wrapper_schedule_count = validated.get("WRAPPER_SCHEDULE_CALL_COUNT")
    agent_schedule_count = validated.get("AGENT_SCHEDULE_CALL_COUNT")
    total_schedule_count = validated.get("TOTAL_SCHEDULE_CALL_COUNT")
    validated["SCHEDULE_CALL_COUNT"] = total_schedule_count
    agent_trace_verification = validated.get("AGENT_TOOL_TRACE_VERIFICATION")
    if agent_trace_verification not in {"VERIFIED", "UNAVAILABLE"}:
        failures.append("INVALID_AGENT_TOOL_TRACE_VERIFICATION")
    if agent_trace_verification == "UNAVAILABLE":
        if agent_schedule_count is not None or total_schedule_count is not None:
            failures.append("UNAVAILABLE_AGENT_TRACE_CANNOT_CLAIM_TOTAL_SCHEDULE_COUNT")
        if validated.get("AGENT_BOUND_RESULT_RETRIEVAL_COUNT") is not None:
            failures.append("UNAVAILABLE_AGENT_TRACE_CANNOT_CLAIM_BOUND_RESULT_COUNT")
    elif agent_trace_verification == "VERIFIED":
        if (
            not isinstance(wrapper_schedule_count, int)
            or not isinstance(agent_schedule_count, int)
            or wrapper_schedule_count < 0
            or agent_schedule_count < 0
        ):
            failures.append("SCHEDULE_COUNT_NOT_INTEGER")
        elif total_schedule_count != wrapper_schedule_count + agent_schedule_count:
            failures.append("TOTAL_SCHEDULE_COUNT_MISMATCH")
        bound_count = validated.get("AGENT_BOUND_RESULT_RETRIEVAL_COUNT")
        if not isinstance(bound_count, int) or bound_count < 0:
            failures.append("AGENT_BOUND_RESULT_RETRIEVAL_COUNT_NOT_INTEGER")
    if (
        validated.get("VISIBLE_SCHEDULE_TOOL_CALL_EXISTS") is True
        and (not isinstance(agent_schedule_count, int) or agent_schedule_count < 1)
    ):
        failures.append("VISIBLE_SCHEDULE_NOT_COUNTED")
    if (
        isinstance(agent_schedule_count, int)
        and agent_schedule_count > 0
        and validated.get("TEST_PROTOCOL_VIOLATION") is not True
    ):
        failures.append("AGENT_SCHEDULE_REQUIRES_PROTOCOL_VIOLATION")
    if (
        validated.get("TEST_PROTOCOL_VIOLATION") is True
        and validated.get("EXPERIMENT_ACCEPTANCE") == "MET"
    ):
        failures.append("PROTOCOL_VIOLATION_CANNOT_MEET_ACCEPTANCE")
    if (
        validated.get("WRAPPER_DELIVERY_STATE") == "DELIVERY_UNKNOWN"
        and validated.get("SAME_MESSAGE_ID_RESEND_ALLOWED") is not False
    ):
        failures.append("DELIVERY_UNKNOWN_MUST_FORBID_RESEND")
    schedule_count_for_validation = total_schedule_count if isinstance(total_schedule_count, int) else 0
    if (
        schedule_count_for_validation > 0
        and float(validated.get("IDLE_WAIT_SECONDS", 0)) <= 0
    ):
        failures.append("SCHEDULE_CALL_HAS_ZERO_IDLE_WAIT")
    if (
        schedule_count_for_validation > 0
        and validated.get("TERMINATED_IMMEDIATELY_AFTER_RESULT") is True
        and validated.get("SCHEDULE_COMPLETED_BEFORE_COMMAND_RESULT_PROVEN") is not True
    ):
        failures.append("SCHEDULE_CONTRADICTS_IMMEDIATE_TERMINATION")
    if (
        validated.get("COMMAND_COMPLETED") is True
        and validated.get("SYNCHRONOUS_COMMAND_COMPLETED") is False
        and validated.get("COMPLETION_MODE") != "BACKGROUND_PROCESS_COMPLETION"
    ):
        failures.append("NONSYNCHRONOUS_COMPLETION_HAS_NO_BACKGROUND_PROCESS")
    if (
        validated.get("COMPLETION_MODE") == "BACKGROUND_PROCESS_COMPLETION"
        and (
            validated.get("BACKGROUND_PROCESS_HANDLE_SUPPORT") is not True
            or validated.get("SUPPORTED_WAIT_OR_RESULT_METHOD") in {None, "", "NONE"}
        )
    ):
        failures.append("BACKGROUND_COMPLETION_HAS_NO_BOUND_RESULT_METHOD")
    if (
        validated.get("TEST_PROTOCOL_VIOLATION") is True
        and validated.get("TEST_RESULT") == "PASS"
    ):
        failures.append("PROTOCOL_VIOLATION_CANNOT_PASS")

    validated["REPORT_VALIDATION_ERRORS"] = failures
    validated["REPORT_VALIDATION"] = "PASS" if not failures else "REPORT_VALIDATION_FAILED"
    validated["REPORT_VALIDATION_FAILED"] = bool(failures)
    if failures:
        validated["PROTOCOL_RESULT"] = "REPORT_VALIDATION_FAILED"
        validated["TEST_RESULT"] = "REPORT_VALIDATION_FAILED"
    return validated


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


def run_opencli(args: list[str], timeout: int) -> dict[str, Any]:
    started = utc_now()
    try:
        completed = subprocess.run(
            [*find_opencli(), *args], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout, check=False,
        )
        return {"started_at": started, "finished_at": utc_now(), "timed_out": False,
                "returncode": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr}
    except subprocess.TimeoutExpired as error:
        return {"started_at": started, "finished_at": utc_now(), "timed_out": True,
                "returncode": None, "stdout": _decode(error.stdout), "stderr": _decode(error.stderr)}


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


def command(
    state: dict[str, Any],
    state_path: Path,
    label: str,
    args: list[str],
    timeout: int,
    before_invoke: Callable[[], None] | None = None,
) -> dict[str, Any] | None:
    if state["external_command_count"] >= state["parameters"]["max_external_commands"]:
        stop(state, "EXPERIMENT_BUDGET_EXHAUSTED: MAX_EXTERNAL_COMMANDS")
        return None
    started = datetime.fromisoformat(state["started_at"])
    elapsed = (datetime.now(timezone.utc) - started).total_seconds()
    if elapsed >= state["parameters"]["max_experiment_seconds"]:
        stop(state, "EXPERIMENT_BUDGET_EXHAUSTED: MAX_EXPERIMENT_SECONDS")
        return None
    if before_invoke:
        before_invoke()
    state["external_command_count"] += 1
    result = run_opencli(args, min(timeout, max(1, int(state["parameters"]["max_experiment_seconds"] - elapsed))))
    save_raw(state, state_path, label, result)
    return result


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


def marker(message_id: str) -> str:
    return f"MESSAGE_ID: {message_id}"


def has_exact_header(text: str, name: str, value: str) -> bool:
    return bool(re.search(
        rf"(?m)^{re.escape(name)}:[ \t]*{re.escape(value)}[ \t]*\r?$", text
    ))


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
    return (f"WORK_ITEM_ID: {args.work_item_id}\nMESSAGE_ID: {args.message_id}\n"
            f"ROUND: {args.round}\nMESSAGE_TYPE: {args.message_type}\n\n" + body.lstrip("\ufeff"))


def read_payload(args: argparse.Namespace) -> str:
    if args.message_file:
        return Path(args.message_file).read_text(encoding="utf-8")
    if sys.stdin.isatty():
        raise ValueError("provide message content on stdin or with --message-file")
    return sys.stdin.read()


def new_state(args: argparse.Namespace, state_path: Path) -> dict[str, Any]:
    return {
        "schema_version": 4, "work_item_id": args.work_item_id, "message_id": args.message_id,
        "operation": "START_NEW_AND_SEND" if args.prepare_new else "SEND",
        "prepare_new": bool(args.prepare_new),
        "round": args.round, "message_type": args.message_type,
        "expected_conversation_mode": "EXISTING" if args.conversation else "NEW",
        "pre_send_active_conversation_id": None, "verified_target_conversation_id": args.conversation,
        "actual_delivery_conversation_id": None, "verified_target_url": None,
        "delivery_state": "NOT_SENT", "work_item_state": "IN_PROGRESS",
        "send_attempt_count": 0, "message_send_count": 0,
        "recovery_attempt_count": 0, "detail_check_count": 0,
        "external_command_count": 0, "misroute_detected": False,
        "read_result": "NOT_RUN", "blank_environment_verified": False,
        "pre_send_already_new": False, "new_command_called": False,
        "browser_navigation_occurred": False,
        "official_response_eligible": False, "started_at": utc_now(), "stopped_at": None,
        "stop_reason": None, "updated_at": utc_now(), "state_file": str(state_path),
        "raw_outputs": [], "transitions": [],
        "post_send_status_url": None, "post_send_active_conversation_id": None,
        "post_send_page_mode": "NOT_RUN", "post_send_history_called": False,
        "post_send_history_available": False, "post_send_recent_conversation_ids": [],
        "new_candidate_diff": [], "recovery_target_source": None,
        "recovery_target_conversation_id": None,
        "parameters": {
            "command_wait_seconds": args.command_wait_seconds,
            "max_send_attempts_per_message": MAX_SEND_ATTEMPTS_PER_MESSAGE,
            "max_recovery_attempts": args.max_recovery_attempts,
            "max_detail_checks": args.max_detail_checks,
            "max_external_commands": args.max_external_commands,
            "max_experiment_seconds": args.max_experiment_seconds,
            "recent_candidate_limit": args.recent_candidate_limit,
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


def detail(state: dict[str, Any], state_path: Path, identity: str) -> tuple[list[dict[str, Any]], str | None]:
    if state["detail_check_count"] >= state["parameters"]["max_detail_checks"]:
        return [], None
    before_command_count = state["external_command_count"]
    result = command(state, state_path, "detail", ["chatgpt", "detail", identity, "-f", "json", "--window", "background"], state["parameters"]["command_wait_seconds"])
    if state["external_command_count"] > before_command_count:
        state["detail_check_count"] += 1
    raw = state["raw_outputs"][-1] if result is not None else None
    return result_rows(result), raw


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


def accept_delivery(state: dict[str, Any], identity: str, ready: bool, response_exists: bool) -> None:
    state["actual_delivery_conversation_id"] = identity
    state["verified_target_conversation_id"] = identity
    state["official_response_eligible"] = True
    set_state(state, "RESPONSE_READY" if ready else ("RESPONSE_PENDING" if response_exists else "DELIVERED"), "exact identifiers found in verified new conversation")
    stop(state, "RESPONSE_READY" if ready else "BOUNDED_WAIT_COMPLETE", "ACHIEVED" if ready else "IN_PROGRESS")


def capture_post_send_status(
    state: dict[str, Any], state_path: Path
) -> dict[str, Any] | None:
    status = command(state, state_path, "status-after-send", ["chatgpt", "status", "-f", "json", "--window", "background"], state["parameters"]["command_wait_seconds"])
    current_url = status_url(status)
    state["post_send_status_url"] = current_url
    state["post_send_active_conversation_id"] = conversation_id_from_url(current_url or "")
    state["post_send_page_mode"] = page_mode(current_url)
    return status


def recover_delivery(
    state: dict[str, Any], state_path: Path,
    returned_identity: str | None = None,
    post_send_status: dict[str, Any] | None = None,
    post_send_status_checked: bool = False,
) -> bool:
    if state["recovery_attempt_count"] >= state["parameters"]["max_recovery_attempts"]:
        stop(state, "EXPERIMENT_BUDGET_EXHAUSTED: MAX_RECOVERY_ATTEMPTS")
        return False
    state["recovery_attempt_count"] += 1
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

    add_candidate(returned_identity, "ASK_REPORTED_CONVERSATION_ID")
    add_candidate(current_id, "POST_SEND_STATUS")
    if len(new_ids) == 1:
        add_candidate(new_ids[0], "POST_SEND_HISTORY_NEW_CANDIDATE_DIFF")
    elif len(new_ids) > 1 and not candidates:
        state["recovery_target_source"] = "AMBIGUOUS_NEW_CANDIDATE_DIFF"
    if candidates:
        identity, source = candidates[0]
        state["recovery_target_source"] = source
        state["recovery_target_conversation_id"] = identity
        messages, raw_path = detail(state, state_path, identity)
        delivered, response_exists, ready = inspect_messages(messages, state["work_item_id"], state["message_id"])
        if delivered:
            if state.get("expected_conversation_mode") == "NEW" and identity in baseline:
                mark_misroute(state, identity, raw_path)
            else:
                accept_delivery(state, identity, ready, response_exists)
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


def send_command(args: argparse.Namespace) -> int:
    if args.prepare_new and (args.conversation or args.manual_new_url):
        raise ValueError("--prepare-new cannot be combined with --conversation or --manual-new-url")
    required_values = {
        "WORK_ITEM_ID": args.work_item_id,
        "MESSAGE_ID": args.message_id,
        "MESSAGE_TYPE": args.message_type,
    }
    for name, value in (
        ("CONVERSATION", args.conversation),
        ("MANUAL_NEW_URL", args.manual_new_url),
        ("MESSAGE_FILE", args.message_file),
        ("STATE_FILE", args.state_file),
    ):
        if value is not None:
            required_values[name] = value
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
    payload = prepare_payload(args, read_payload(args))
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
        state["send_attempt_count"] = 1
        state["message_send_count"] = 1
        write_json(state_path, state)

    result = command(
        state,
        state_path,
        "ask",
        ["chatgpt", "ask", payload, *target, "--timeout", str(args.command_wait_seconds), "-f", "json", "--window", "background"],
        args.command_wait_seconds + 5,
        before_invoke=mark_send_invoked,
    )
    if result is None:
        write_json(state_path, state)
        return output_state(state)
    returned_id, returned_url = ask_identity(result)
    state["ask_return_code"] = result.get("returncode")
    state["ask_timed_out"] = bool(result.get("timed_out"))
    state["ask_error_code"] = cli_error_code(str(result.get("stderr") or ""))
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
    if result["timed_out"] or result["returncode"] != 0:
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
        state["verified_target_conversation_id"] = returned_id
        state["official_response_eligible"] = True
        response = ask_response(result)
        set_state(state, "RESPONSE_READY" if response else "DELIVERED", "ask returned verified new conversation identity")
        stop(state, "RESPONSE_READY" if response else "BOUNDED_WAIT_COMPLETE", "ACHIEVED" if response else "IN_PROGRESS")
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
    if state.get("delivery_state") == "MISROUTED_DELIVERY":
        return output_state(state)
    recover_delivery(state, state_path, state.get("actual_delivery_conversation_id"))
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
    recover = sub.add_parser("recover", help="one bounded exact-ID recovery without sending")
    recover.add_argument("--state-file", required=True)
    recover.set_defaults(handler=recover_command)
    cleanup = sub.add_parser("cleanup")
    cleanup.add_argument("--state-file", required=True)
    cleanup.set_defaults(handler=cleanup_command)
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
