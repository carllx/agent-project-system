"""Pure-local validation for bounded RR Lead experiment traces."""

from __future__ import annotations

import re
from typing import Any

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
