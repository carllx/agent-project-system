"""Pure-local public-CLI tests for the RR Lead OpenCLI transport."""

from __future__ import annotations

import json
import importlib.util
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TRANSPORT = ROOT / "skills" / "research-review-lead" / "scripts" / "opencli_transport.py"
REAL_EMPTY_RESULT_FIXTURE = ROOT / "scripts" / "fixtures" / "transport-a2p1-read-empty-result.json"
REAL_A2P2_EMPTY_RESULT_FIXTURE = ROOT / "scripts" / "fixtures" / "transport-a2p2-read-empty-result.json"
sys.dont_write_bytecode = True
OLD_ID = "old-conversation"
WORK_ITEM = "SYNTHETIC-A2P1-001"
LEGACY_WORK_ITEM = "SYNTHETIC-TRANSPORT-001"
LEGACY_MESSAGE_ID = f"{LEGACY_WORK_ITEM}-R0-SMOKE"
NEW_ID = "new-conversation"

TRANSPORT_SPEC = importlib.util.spec_from_file_location("rr_opencli_transport", TRANSPORT)
assert TRANSPORT_SPEC and TRANSPORT_SPEC.loader
TRANSPORT_MODULE = importlib.util.module_from_spec(TRANSPORT_SPEC)
TRANSPORT_SPEC.loader.exec_module(TRANSPORT_MODULE)

FAKE_OPENCLI = r'''import json, os, sys, time
scenario_path = os.environ["OPENCLI_FAKE_SCENARIO"]
counter_path = os.environ["OPENCLI_FAKE_COUNTER"]
log_path = os.environ["OPENCLI_FAKE_LOG"]
scenario = json.loads(open(scenario_path, encoding="utf-8").read())
try:
    index = int(open(counter_path, encoding="utf-8").read())
except (FileNotFoundError, ValueError):
    index = 0
open(counter_path, "w", encoding="utf-8").write(str(index + 1))
with open(log_path, "a", encoding="utf-8") as stream:
    stream.write(json.dumps(sys.argv[1:]) + "\n")
item = scenario[index]
time.sleep(2 if item.get("timed_out") else item.get("sleep", 0))
sys.stdout.write(item.get("stdout", ""))
sys.stderr.write(item.get("stderr", ""))
raise SystemExit(item.get("returncode", 0))
'''


def response(value: object, **extra: object) -> dict[str, object]:
    return {"stdout": value if isinstance(value, str) else json.dumps(value), **extra}


def status(url: str) -> dict[str, object]:
    return response([{"Status": "Connected", "Login": "Yes", "Url": url}])


def run_prepare(
    sequence: list[dict[str, object]], *, extra_args: list[str] | None = None
) -> tuple[subprocess.CompletedProcess[str], dict, list[list[str]], Path]:
    root = Path(tempfile.mkdtemp(prefix="rr-prepare-new-test-"))
    fake = root / "fake_opencli.py"
    fake.write_text(FAKE_OPENCLI, encoding="utf-8")
    scenario = root / "scenario.json"
    scenario.write_text(json.dumps(sequence), encoding="utf-8")
    counter = root / "counter.txt"
    log = root / "calls.jsonl"
    runtime = root / "runtime"
    env = os.environ.copy()
    env.update({
        "OPENCLI_TRANSPORT_EXECUTABLE": str(fake),
        "OPENCLI_FAKE_SCENARIO": str(scenario),
        "OPENCLI_FAKE_COUNTER": str(counter),
        "OPENCLI_FAKE_LOG": str(log),
    })
    command = [sys.executable, str(TRANSPORT), "prepare-new", "--runtime-dir", str(runtime),
               "--work-item-id", WORK_ITEM, *(extra_args or [])]
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", env=env, check=False)
    state = json.loads((runtime / "prepare-new-state.json").read_text(encoding="utf-8"))
    calls = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []
    return completed, state, calls, runtime


def success_sequence(
    read: object = "EMPTY_RESULT", post_url: str = "https://chatgpt.com/new",
    pre_url: str = f"https://chatgpt.com/c/{OLD_ID}",
) -> list[dict[str, object]]:
    return [
        status(pre_url),
        response([{"Status": "New conversation started"}]),
        status(post_url),
        response(read),
    ]


def assert_no_send(calls: list[list[str]]) -> None:
    verbs = [call[1] for call in calls if len(call) > 1 and call[0] == "chatgpt"]
    assert "ask" not in verbs and "send" not in verbs, verbs


def test_help_exposes_prepare_new() -> None:
    completed = subprocess.run([sys.executable, str(TRANSPORT), "--help"], capture_output=True,
                               text=True, encoding="utf-8", check=False)
    assert completed.returncode == 0
    assert "prepare-new" in completed.stdout


def test_help_exposes_require_existing_conversation() -> None:
    completed = subprocess.run(
        [sys.executable, str(TRANSPORT), "prepare-new", "--help"],
        capture_output=True, text=True, encoding="utf-8", check=False,
    )
    assert completed.returncode == 0
    assert "--require-existing-conversation" in completed.stdout


def test_old_conversation_to_new_and_empty_result() -> None:
    completed, state, calls, runtime = run_prepare(
        success_sequence(), extra_args=["--require-existing-conversation"]
    )
    assert completed.returncode == 0
    assert state["test_result"] == "PREPARED_NEW_CONVERSATION"
    assert state["pre_operation_conversation_id"] == OLD_ID
    assert state["post_operation_url"] == "https://chatgpt.com/new"
    assert state["read_result"] == "EMPTY"
    assert state["verification_result"] == "NEW_BLANK_CONVERSATION_VERIFIED"
    assert state["pre_operation_mode"] == "EXISTING_CONVERSATION"
    assert state["require_existing_conversation"] is True
    assert state["precondition_checked"] is True
    assert state["precondition_met"] is True
    assert state["new_command_called"] is True
    assert state["conversation_transition_verified"] is True
    assert state["blank_environment_verified"] is True
    assert state["message_send_count"] == 0
    assert (runtime / "prepare-new-state.json").is_file()
    assert_no_send(calls)


def test_real_empty_result_format_regression() -> None:
    real_read = json.loads(REAL_EMPTY_RESULT_FIXTURE.read_text(encoding="utf-8"))
    sequence = success_sequence()
    sequence[-1] = real_read
    completed, state, calls, _ = run_prepare(sequence)
    assert completed.returncode == 0
    assert state["read_result"] == "EMPTY"
    assert state["verification_result"] == "NEW_BLANK_CONVERSATION_VERIFIED"
    assert state["test_result"] == "PREPARED_NEW_CONVERSATION"
    assert_no_send(calls)


def test_nonzero_exact_empty_result_code_verifies_blank_page() -> None:
    read = response("", returncode=73, stderr="ok: false\nerror:\n  code: EMPTY_RESULT\n  exitCode: 73\n")
    completed, state, calls, _ = run_prepare(success_sequence()[:-1] + [read])
    assert completed.returncode == 0
    assert state["read_result"] == "EMPTY"
    assert_no_send(calls)


def test_empty_json_object_or_array_verifies_blank_page() -> None:
    for value in ({}, []):
        completed, state, calls, _ = run_prepare(success_sequence(value))
        assert completed.returncode == 0
        assert state["test_result"] == "PREPARED_NEW_CONVERSATION"
        assert state["read_result"] == "EMPTY"
        assert_no_send(calls)


def test_runtime_contains_required_a2p1_fields() -> None:
    _, state, _, _ = run_prepare(success_sequence())
    required = {
        "work_item_id", "operation", "pre_operation_url",
        "require_existing_conversation", "precondition_checked",
        "precondition_met", "new_command_called",
        "pre_operation_conversation_id", "post_operation_url",
        "pre_operation_mode", "conversation_transition_verified",
        "blank_environment_verified",
        "verification_result", "read_result", "message_send_count",
        "external_command_count", "started_at", "stopped_at",
        "elapsed_seconds", "stop_reason", "test_result",
        "placeholder_validation_performed", "unresolved_placeholders",
        "wrapper_schedule_call_count", "agent_schedule_call_count",
        "total_schedule_call_count", "agent_bound_result_retrieval_count",
        "agent_tool_trace_verification", "idle_wait_seconds", "poll_attempt_count",
        "background_result_check_count", "background_wait_seconds",
        "background_process_handle_support", "supported_wait_or_result_method",
        "completion_mode", "test_protocol_violation", "report_validation",
        "synchronous_command_completed", "terminated_immediately_after_result",
    }
    assert required <= state.keys()
    assert state["operation"] == "PREPARE_NEW"
    assert state["message_send_count"] == 0
    assert state["external_command_count"] == 4
    assert state["parameters"]["max_recovery_attempts"] == 0
    assert state["parameters"]["max_detail_checks"] == 0
    assert state["placeholder_validation_performed"] is True
    assert state["unresolved_placeholders"] == []
    assert state["wrapper_schedule_call_count"] == 0
    assert state["agent_schedule_call_count"] is None
    assert state["total_schedule_call_count"] is None
    assert state["agent_tool_trace_verification"] == "UNAVAILABLE"
    assert state["idle_wait_seconds"] == 0
    assert state["poll_attempt_count"] == 0
    assert state["synchronous_command_completed"] is True
    assert state["terminated_immediately_after_result"] is True
    assert state["completion_mode"] == "SYNCHRONOUS_COMPLETION"
    assert state["background_result_check_count"] == 0
    assert state["report_validation"] == "PASS"


def protocol_report(
    value: object,
    events: list[dict[str, object]] | None = None,
    **overrides: object,
) -> dict:
    return TRANSPORT_MODULE.assess_experiment_protocol(
        {"EXPECTED_CONVERSATION_URL": value}, events or [], **overrides
    )


def validate_report(overrides: dict[str, object]) -> dict:
    report: dict[str, object] = {
        "WRAPPER_SCHEDULE_CALL_COUNT": 0,
        "AGENT_SCHEDULE_CALL_COUNT": 0,
        "TOTAL_SCHEDULE_CALL_COUNT": 0,
        "AGENT_TOOL_TRACE_VERIFICATION": "VERIFIED",
        "AGENT_BOUND_RESULT_RETRIEVAL_COUNT": 0,
        "EXPERIMENT_ACCEPTANCE": "NOT_MET",
        "IDLE_WAIT_SECONDS": 0,
        "TEST_PROTOCOL_VIOLATION": False,
        "TEST_RESULT": "BLOCKED",
    }
    report.update(overrides)
    return TRANSPORT_MODULE.validate_experiment_report(report)


def synchronous_status_event() -> dict[str, object]:
    return {
        "action": "SHELL_COMMAND",
        "result": {"exit_code": 0, "stdout": "Status: Connected", "stderr": ""},
    }


def test_real_conversation_url_can_execute() -> None:
    report = protocol_report(
        "https://chatgpt.com/c/6a6c3b12-0064-4e2f-9ee1-123456789abc",
        [synchronous_status_event()],
    )
    assert report["PROTOCOL_RESULT"] == "PASS"
    assert report["UNRESOLVED_PLACEHOLDERS"] == []
    assert report["EXTERNAL_COMMAND_COUNT"] == 1


def test_angle_id_placeholder_is_rejected() -> None:
    report = protocol_report("https://chatgpt.com/c/<id>")
    assert report["PROTOCOL_RESULT"] == "BLOCKED_BEFORE_EXECUTION"
    assert report["UNRESOLVED_PLACEHOLDERS"] == ["EXPECTED_CONVERSATION_URL"]


def test_chinese_paste_placeholder_is_rejected() -> None:
    report = protocol_report("请在这里粘贴 Conversation URL")
    assert report["PROTOCOL_RESULT"] == "BLOCKED_BEFORE_EXECUTION"


def test_empty_required_value_is_rejected() -> None:
    for value in ("", "   ", None):
        report = protocol_report(value)
        assert report["PROTOCOL_RESULT"] == "BLOCKED_BEFORE_EXECUTION"


def test_placeholder_failure_has_zero_external_commands() -> None:
    for value in ("TODO", "TBD", "PLACEHOLDER", "https://example.com/value"):
        report = protocol_report(value)
        assert report["PLACEHOLDER_VALIDATION_PERFORMED"] is True
        assert report["EXTERNAL_COMMAND_COUNT"] == 0
        assert report["EXPERIMENT_ACTION_COUNT"] == 0


def test_send_placeholder_is_blocked_before_opencli() -> None:
    root = Path(tempfile.mkdtemp(prefix="rr-placeholder-send-test-"))
    fake = root / "fake_opencli.py"
    fake.write_text(FAKE_OPENCLI, encoding="utf-8")
    scenario = root / "scenario.json"
    scenario.write_text("[]", encoding="utf-8")
    log = root / "calls.jsonl"
    message_file = root / "message.txt"
    message_file.write_text("synthetic body", encoding="utf-8")
    env = os.environ.copy()
    env.update({
        "OPENCLI_TRANSPORT_EXECUTABLE": str(fake),
        "OPENCLI_FAKE_SCENARIO": str(scenario),
        "OPENCLI_FAKE_COUNTER": str(root / "counter.txt"),
        "OPENCLI_FAKE_LOG": str(log),
    })
    completed = subprocess.run(
        [
            sys.executable, str(TRANSPORT), "send",
            "--work-item-id", "TODO",
            "--message-id", "TODO",
            "--round", "0",
            "--message-type", "CONTEXT_PACKET",
            "--message-file", str(message_file),
        ],
        capture_output=True, text=True, encoding="utf-8", env=env, check=False,
    )
    report = json.loads(completed.stdout)
    assert completed.returncode == 2
    assert report["test_result"] == "BLOCKED_BEFORE_EXECUTION"
    assert report["EXTERNAL_COMMAND_COUNT"] == 0
    assert not log.exists()


def test_synchronous_status_terminates_immediately() -> None:
    report = protocol_report("https://chatgpt.com/c/real-id", [synchronous_status_event()])
    assert report["SYNCHRONOUS_COMMAND_COMPLETED"] is True
    assert report["TERMINATED_IMMEDIATELY_AFTER_RESULT"] is True
    assert report["SCHEDULE_CALL_COUNT"] == 0
    assert report["IDLE_WAIT_SECONDS"] == 0
    assert report["POLL_ATTEMPT_COUNT"] == 0
    assert report["COMPLETION_MODE"] == "SYNCHRONOUS_COMPLETION"


def test_two_second_foreground_trace_is_synchronous() -> None:
    event = synchronous_status_event()
    event["foreground_return_seconds"] = 2
    report = protocol_report("https://chatgpt.com/c/real-id", [event])
    assert report["PROTOCOL_RESULT"] == "PASS"
    assert report["COMPLETION_MODE"] == "SYNCHRONOUS_COMPLETION"


def test_seven_second_foreground_trace_is_synchronous() -> None:
    event = synchronous_status_event()
    event["foreground_return_seconds"] = 7
    report = protocol_report("https://chatgpt.com/c/real-id", [event])
    assert report["PROTOCOL_RESULT"] == "PASS"
    assert report["BACKGROUND_PROCESS_HANDLE_SUPPORT"] is False


def test_schedule_after_synchronous_result_is_protocol_violation() -> None:
    report = protocol_report(
        "https://chatgpt.com/c/real-id",
        [synchronous_status_event(), {"action": "SCHEDULE", "seconds": 300}],
    )
    assert report["PROTOCOL_RESULT"] == "TEST_PROTOCOL_VIOLATION"
    assert "UNAUTHORIZED_IDLE_WAIT" in report["FAILURE_TYPES"]
    assert report["SCHEDULE_CALL_COUNT"] == 1
    assert report["IDLE_WAIT_SECONDS"] == 300
    assert report["TERMINATED_IMMEDIATELY_AFTER_RESULT"] is False
    assert report["WHO_INITIATED_SCHEDULE"] == "UNKNOWN"


def test_background_wait_without_handle_is_rejected() -> None:
    report = protocol_report(
        "https://chatgpt.com/c/real-id",
        [
            {"action": "TOOL_RESULT", "status": "RUNNING", "result_method": "wait"},
            {"action": "BACKGROUND_RESULT_CHECK", "seconds": 7},
        ],
        polling_authorized=True,
    )
    assert report["PROTOCOL_RESULT"] == "TEST_PROTOCOL_VIOLATION"
    assert "UNBOUND_OR_UNSUPPORTED_BACKGROUND_WAIT" in report["FAILURE_TYPES"]


def test_bound_background_result_is_read_once_within_fifteen_seconds() -> None:
    events = [
        {
            "action": "TOOL_RESULT", "status": "RUNNING",
            "process_handle": "process-7s", "result_method": "wait_process",
        },
        {
            "action": "BACKGROUND_RESULT_CHECK", "process_handle": "process-7s",
            "seconds": 7,
            "result": {"exit_code": 0, "stdout": "PROBE_7S_DONE", "stderr": ""},
        },
    ]
    report = protocol_report("https://chatgpt.com/c/real-id", events, polling_authorized=True)
    assert report["PROTOCOL_RESULT"] == "PASS"
    assert report["BACKGROUND_RESULT_CHECK_COUNT"] == 1
    assert report["BACKGROUND_WAIT_SECONDS"] == 7
    assert report["SUPPORTED_WAIT_OR_RESULT_METHOD"] == "wait_process"

    repeated = protocol_report(
        "https://chatgpt.com/c/real-id",
        events + [{"action": "BACKGROUND_RESULT_CHECK", "process_handle": "process-7s"}],
        polling_authorized=True,
    )
    assert repeated["PROTOCOL_RESULT"] == "TEST_PROTOCOL_VIOLATION"
    assert "BACKGROUND_RESULT_CHECK_BUDGET_EXCEEDED" in repeated["FAILURE_TYPES"]


def test_background_completion_is_not_synchronous_completion() -> None:
    report = protocol_report(
        "https://chatgpt.com/c/real-id",
        [
            {
                "action": "TOOL_RESULT", "status": "RUNNING",
                "process_handle": "process-7s", "result_method": "wait_process",
            },
            {
                "action": "BACKGROUND_RESULT_CHECK", "process_handle": "process-7s",
                "seconds": 7,
                "result": {"exit_code": 0, "stdout": "done", "stderr": ""},
            },
        ],
        polling_authorized=True,
    )
    assert report["COMMAND_COMPLETED"] is True
    assert report["SYNCHRONOUS_COMMAND_COMPLETED"] is False
    assert report["COMPLETION_MODE"] == "BACKGROUND_PROCESS_COMPLETION"


def test_schedule_call_cannot_report_zero_wait() -> None:
    report = validate_report({
        "AGENT_SCHEDULE_CALL_COUNT": 1,
        "TOTAL_SCHEDULE_CALL_COUNT": 1,
        "IDLE_WAIT_SECONDS": 0,
        "TERMINATED_IMMEDIATELY_AFTER_RESULT": False,
        "TEST_PROTOCOL_VIOLATION": True,
        "TEST_RESULT": "TEST_PROTOCOL_VIOLATION",
    })
    assert report["REPORT_VALIDATION"] == "REPORT_VALIDATION_FAILED"
    assert "SCHEDULE_CALL_HAS_ZERO_IDLE_WAIT" in report["REPORT_VALIDATION_ERRORS"]


def test_protocol_violation_cannot_return_pass() -> None:
    report = validate_report({
        "AGENT_SCHEDULE_CALL_COUNT": 0,
        "TOTAL_SCHEDULE_CALL_COUNT": 0,
        "IDLE_WAIT_SECONDS": 0,
        "TERMINATED_IMMEDIATELY_AFTER_RESULT": False,
        "TEST_PROTOCOL_VIOLATION": True,
        "TEST_RESULT": "PASS",
    })
    assert report["TEST_RESULT"] == "REPORT_VALIDATION_FAILED"
    assert "PROTOCOL_VIOLATION_CANNOT_PASS" in report["REPORT_VALIDATION_ERRORS"]


def test_contradictory_report_fails_validation() -> None:
    report = validate_report({
        "AGENT_SCHEDULE_CALL_COUNT": 1,
        "TOTAL_SCHEDULE_CALL_COUNT": 1,
        "IDLE_WAIT_SECONDS": 300,
        "TERMINATED_IMMEDIATELY_AFTER_RESULT": True,
        "SCHEDULE_COMPLETED_BEFORE_COMMAND_RESULT_PROVEN": False,
        "COMMAND_COMPLETED": True,
        "SYNCHRONOUS_COMMAND_COMPLETED": False,
        "COMPLETION_MODE": "SYNCHRONOUS_COMPLETION",
        "TEST_PROTOCOL_VIOLATION": False,
        "TEST_RESULT": "PASS",
    })
    assert report["PROTOCOL_RESULT"] == "REPORT_VALIDATION_FAILED"
    assert set(report["REPORT_VALIDATION_ERRORS"]) == {
        "AGENT_SCHEDULE_REQUIRES_PROTOCOL_VIOLATION",
        "SCHEDULE_CONTRADICTS_IMMEDIATE_TERMINATION",
        "NONSYNCHRONOUS_COMPLETION_HAS_NO_BACKGROUND_PROCESS",
    }


def test_unauthorized_sleep_is_protocol_violation() -> None:
    report = protocol_report(
        "https://chatgpt.com/c/real-id", [{"action": "SLEEP", "seconds": 2}]
    )
    assert report["PROTOCOL_RESULT"] == "TEST_PROTOCOL_VIOLATION"
    assert "UNAUTHORIZED_IDLE_WAIT" in report["FAILURE_TYPES"]


def test_poll_requires_authorized_running_job() -> None:
    allowed = protocol_report(
        "https://chatgpt.com/c/real-id",
        [
            {
                "action": "TOOL_RESULT", "status": "RUNNING", "job_id": "job-123",
                "result_method": "read_job_result",
            },
            {
                "action": "BACKGROUND_RESULT_CHECK", "job_id": "job-123", "seconds": 1,
                "result": {"exit_code": 0, "stdout": "done", "stderr": ""},
            },
        ],
        polling_authorized=True,
        max_idle_wait_seconds=1,
        max_poll_attempts=1,
    )
    assert allowed["PROTOCOL_RESULT"] == "PASS"
    assert allowed["BACKGROUND_RESULT_CHECK_COUNT"] == 1
    for events in (
        [{"action": "TOOL_RESULT", "status": "RUNNING"}, {"action": "POLL"}],
        [{"action": "TOOL_RESULT", "status": "COMPLETE", "job_id": "job-123"}, {"action": "POLL"}],
    ):
        denied = protocol_report(
            "https://chatgpt.com/c/real-id",
            events,
            polling_authorized=True,
            max_poll_attempts=1,
        )
        assert denied["PROTOCOL_RESULT"] == "TEST_PROTOCOL_VIOLATION"


def test_all_experiment_actions_are_counted() -> None:
    actions = [
        "SHELL_COMMAND", "SCHEDULE", "SLEEP", "TIMER", "POLL",
        "FILE_SEARCH", "SOURCE_SEARCH", "LOG_SEARCH",
    ]
    report = protocol_report(
        "https://chatgpt.com/c/real-id",
        [{"action": action} for action in actions],
        max_external_commands=1,
    )
    assert report["EXPERIMENT_ACTION_COUNT"] == len(actions)
    assert all(report["ACTION_COUNTS"][action] == 1 for action in actions)


def test_old_conversation_still_active_fails() -> None:
    completed, state, calls, _ = run_prepare(success_sequence(post_url=f"https://chatgpt.com/c/{OLD_ID}"))
    assert completed.returncode == 2
    assert state["test_result"] == "BLOCKED_BEFORE_SEND"
    assert state["verification_result"] == "FAILED"
    assert_no_send(calls)


def test_existing_messages_fail() -> None:
    completed, state, calls, _ = run_prepare(success_sequence([{"Role": "user", "Text": "existing"}]))
    assert completed.returncode == 2
    assert state["read_result"] == "NON_EMPTY"
    assert state["test_result"] == "BLOCKED_BEFORE_SEND"
    assert state["stop_reason"] == "READ_NOT_EMPTY"
    assert_no_send(calls)


def test_unknown_error_code_is_unparseable() -> None:
    read = response("", returncode=66, stderr="ok: false\nerror:\n  code: SELECTOR_FAILED\n")
    completed, state, calls, _ = run_prepare(success_sequence()[:-1] + [read])
    assert completed.returncode == 2
    assert state["read_result"] == "UNPARSEABLE"
    assert state["stop_reason"] == "READ_UNPARSEABLE"
    assert_no_send(calls)


def test_unparseable_output_blocks_before_send() -> None:
    completed, state, calls, _ = run_prepare(success_sequence("not-json-or-empty-result"))
    assert completed.returncode == 2
    assert state["read_result"] == "UNPARSEABLE"
    assert state["stop_reason"] == "READ_UNPARSEABLE"
    assert_no_send(calls)


def test_already_new_reports_no_conversation_transition() -> None:
    completed, state, calls, _ = run_prepare(success_sequence(pre_url="https://chatgpt.com/new"))
    assert completed.returncode == 0
    assert state["pre_operation_mode"] == "ALREADY_NEW"
    assert state["conversation_transition_verified"] is False
    assert state["blank_environment_verified"] is True
    assert_no_send(calls)


def assert_precondition_blocked(pre_url: str) -> tuple[dict, list[list[str]]]:
    completed, state, calls, _ = run_prepare(
        [status(pre_url)], extra_args=["--require-existing-conversation"]
    )
    assert completed.returncode == 2
    assert state["test_result"] == "BLOCKED_BEFORE_EXECUTION"
    assert state["stop_reason"] == "EXISTING_CONVERSATION_PRECONDITION_NOT_MET"
    assert state["require_existing_conversation"] is True
    assert state["precondition_checked"] is True
    assert state["precondition_met"] is False
    assert state["new_command_called"] is False
    assert state["conversation_transition_verified"] is False
    assert state["blank_environment_verified"] is False
    assert state["message_send_count"] == 0
    assert state["external_command_count"] == 1
    assert [call[1] for call in calls] == ["status"]
    assert_no_send(calls)
    return state, calls


def test_required_existing_from_new_stops_before_new() -> None:
    state, calls = assert_precondition_blocked("https://chatgpt.com/new")
    assert state["pre_operation_mode"] == "ALREADY_NEW"
    assert all(call[1] not in {"new", "read"} for call in calls)


def test_required_existing_from_root_stops_before_new() -> None:
    state, calls = assert_precondition_blocked("https://chatgpt.com/")
    assert state["pre_operation_mode"] == "ALREADY_NEW"
    assert all(call[1] not in {"new", "read"} for call in calls)


def test_required_existing_rejects_invalid_conversation_url() -> None:
    invalid_urls = [
        "https://chatgpt.com/c/",
        "https://chatgpt.com/c/not-valid/extra",
        "https://example.com/c/not-a-chatgpt-conversation",
    ]
    for url in invalid_urls:
        state, calls = assert_precondition_blocked(url)
        assert state["pre_operation_mode"] == "UNKNOWN"
        assert state["pre_operation_conversation_id"] is None
        assert all(call[1] not in {"new", "read"} for call in calls)


def test_prepare_without_requirement_remains_compatible() -> None:
    completed, state, calls, _ = run_prepare(
        success_sequence(pre_url="https://chatgpt.com/new")
    )
    assert completed.returncode == 0
    assert state["test_result"] == "PREPARED_NEW_CONVERSATION"
    assert state["require_existing_conversation"] is False
    assert state["precondition_checked"] is True
    assert state["precondition_met"] is False
    assert state["new_command_called"] is True
    assert state["message_send_count"] == 0
    assert [call[1] for call in calls] == ["status", "new", "status", "read"]
    assert_no_send(calls)


def test_old_conversation_reports_verified_transition() -> None:
    completed, state, calls, _ = run_prepare(success_sequence())
    assert completed.returncode == 0
    assert state["pre_operation_mode"] == "EXISTING_CONVERSATION"
    assert state["conversation_transition_verified"] is True
    assert state["blank_environment_verified"] is True
    assert_no_send(calls)


def test_all_read_failures_remain_zero_send() -> None:
    failures = [
        response([{"Role": "assistant", "Text": "existing"}]),
        response("not-json"),
        response("", returncode=66, stderr="error:\n  code: UNKNOWN\n"),
    ]
    for read in failures:
        completed, state, calls, _ = run_prepare(success_sequence()[:-1] + [read])
        assert completed.returncode == 2
        assert state["test_result"] == "BLOCKED_BEFORE_SEND"
        assert state["message_send_count"] == 0
        assert_no_send(calls)


def test_sixty_second_budget_is_machine_enforced() -> None:
    sequence = success_sequence()
    sequence[0]["sleep"] = 0.05
    completed, state, calls, _ = run_prepare(
        sequence, extra_args=["--max-experiment-seconds", "0.01"]
    )
    assert completed.returncode == 2
    assert state["test_result"] == "BUDGET_EXHAUSTED"
    assert state["stop_reason"] == "BUDGET_EXHAUSTED"
    assert state["external_command_count"] <= 1
    assert_no_send(calls)


def test_prepare_never_calls_ask_or_send() -> None:
    _, state, calls, _ = run_prepare(success_sequence())
    assert state["message_send_count"] == 0
    assert_no_send(calls)


def test_external_command_budget_stops_before_next_command() -> None:
    completed, state, calls, _ = run_prepare(
        success_sequence(), extra_args=["--max-external-commands", "3"]
    )
    assert completed.returncode == 2
    assert state["test_result"] == "BUDGET_EXHAUSTED"
    assert state["external_command_count"] == 3
    assert len(calls) == 3
    assert_no_send(calls)


def legacy_result(
    stdout: object = None, *, returncode: int = 0, timed_out: bool = False, stderr: str = ""
) -> dict:
    return {
        "started_at": "2026-08-05T00:00:00+00:00",
        "finished_at": "2026-08-05T00:00:01+00:00",
        "timed_out": timed_out,
        "returncode": returncode,
        "stdout": stdout if isinstance(stdout, str) else json.dumps(stdout if stdout is not None else []),
        "stderr": stderr,
    }


def send_cli_command(
    root: Path, *, max_external_commands: int = 9, manual_new_url: str | None = None,
    conversation: str | None = None, prepare_new: bool = False,
) -> list[str]:
    message_file = root / "message.txt"
    message_file.write_text("synthetic body", encoding="utf-8")
    command = [
        sys.executable, str(TRANSPORT), "send",
        "--work-item-id", LEGACY_WORK_ITEM,
        "--message-id", LEGACY_MESSAGE_ID,
        "--round", "0",
        "--message-type", "TRANSPORT_SMOKE",
        "--message-file", str(message_file),
        "--state-file", str(root / "state.json"),
        "--command-wait-seconds", "1",
        "--max-recovery-attempts", "1",
        "--max-detail-checks", "1",
        "--max-external-commands", str(max_external_commands),
        "--max-experiment-seconds", "60",
        "--recent-candidate-limit", "3",
    ]
    if manual_new_url:
        command.extend(["--manual-new-url", manual_new_url])
    if conversation:
        command.extend(["--conversation", conversation])
    if prepare_new:
        command.append("--prepare-new")
    return command


def run_send_case(
    sequence: list[dict], *, max_external_commands: int = 9,
    manual_new_url: str | None = None, conversation: str | None = None,
    prepare_new: bool = False,
) -> tuple[subprocess.CompletedProcess[str], dict, list[list[str]], list[str], dict[str, str]]:
    root = Path(tempfile.mkdtemp(prefix="rr-send-regression-"))
    fake = root / "fake_opencli.py"
    fake.write_text(FAKE_OPENCLI, encoding="utf-8")
    scenario = root / "scenario.json"
    scenario.write_text(json.dumps(sequence), encoding="utf-8")
    counter = root / "counter.txt"
    log = root / "calls.jsonl"
    env = os.environ.copy()
    env.update({
        "OPENCLI_TRANSPORT_EXECUTABLE": str(fake),
        "OPENCLI_FAKE_SCENARIO": str(scenario),
        "OPENCLI_FAKE_COUNTER": str(counter),
        "OPENCLI_FAKE_LOG": str(log),
    })
    command = send_cli_command(
        root, max_external_commands=max_external_commands, manual_new_url=manual_new_url,
        conversation=conversation, prepare_new=prepare_new,
    )
    completed = subprocess.run(
        command, capture_output=True, text=True, encoding="utf-8", env=env, check=False
    )
    state = json.loads((root / "state.json").read_text(encoding="utf-8"))
    calls = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert len(calls) <= max_external_commands
    return completed, state, calls, command, env


def legacy_status(url: str) -> dict:
    return legacy_result([{"Status": "Connected", "Login": "Yes", "Url": url}])


def legacy_history(*identities: str) -> dict:
    selected = identities or (OLD_ID,)
    return legacy_result([
        {"Id": identity, "Title": "candidate", "Url": f"https://chatgpt.com/c/{identity}"}
        for identity in selected
    ])


def legacy_detail(ready: bool = True) -> dict:
    messages = [{"Role": "user", "Text": f"WORK_ITEM_ID: {LEGACY_WORK_ITEM}\nMESSAGE_ID: {LEGACY_MESSAGE_ID}"}]
    if ready:
        messages.append({"Role": "assistant", "Text": "synthetic response", "Generating": False, "StableSeconds": 3})
    return legacy_result(messages)


def recovery_sequence(
    *, ask: dict | None = None, post_url: str = "https://chatgpt.com/",
    post_history: dict | None = None, detail_result: dict | None = None,
) -> list[dict]:
    return [
        legacy_status("https://chatgpt.com/new"),
        legacy_history(OLD_ID),
        legacy_result([]),
        ask or legacy_result([{"response": "completed without identity"}]),
        legacy_status(post_url),
        post_history or legacy_history(OLD_ID, NEW_ID),
        detail_result or legacy_detail(),
    ]


def test_send_correct_new_conversation_regression() -> None:
    completed, state, _, _, _ = run_send_case([
        legacy_status(f"https://chatgpt.com/c/{OLD_ID}"), legacy_history(),
        legacy_result([{"Status": "New conversation started"}]),
        legacy_status("https://chatgpt.com/new"), legacy_result([]),
        legacy_result([{"conversationId": NEW_ID, "conversationUrl": f"https://chatgpt.com/c/{NEW_ID}", "response": "ok"}]),
    ])
    assert completed.returncode == 0
    assert state["delivery_state"] == "RESPONSE_READY"
    assert state["send_attempt_count"] == 1
    assert state["message_send_count"] == 1


def test_send_help_exposes_integrated_prepare_new() -> None:
    completed = subprocess.run(
        [sys.executable, str(TRANSPORT), "send", "--help"],
        capture_output=True, text=True, encoding="utf-8", check=False,
    )
    assert completed.returncode == 0
    assert "--prepare-new" in completed.stdout
    assert "START_NEW_AND_SEND" in completed.stdout


def test_start_new_and_send_completes_in_one_wrapper_call() -> None:
    completed, state, calls, _, _ = run_send_case([
        legacy_history(OLD_ID),
        legacy_status(f"https://chatgpt.com/c/{OLD_ID}"),
        legacy_result([{"Status": "New conversation started"}]),
        legacy_status("https://chatgpt.com/new"),
        legacy_result([]),
        legacy_result([{
            "conversationId": NEW_ID,
            "conversationUrl": f"https://chatgpt.com/c/{NEW_ID}",
            "response": "ok",
        }]),
        legacy_status(f"https://chatgpt.com/c/{NEW_ID}"),
    ], prepare_new=True)
    verbs = [call[1] for call in calls]
    assert completed.returncode == 0
    assert verbs == ["history", "status", "new", "status", "read", "ask", "status"]
    assert state["operation"] == "START_NEW_AND_SEND"
    assert state["prepare_new"] is True
    assert state["new_command_called"] is True
    assert state["blank_environment_verified"] is True
    assert state["send_attempt_count"] == 1
    assert state["message_send_count"] == 1
    assert state["post_send_active_conversation_id"] == NEW_ID
    assert state["delivery_state"] == "RESPONSE_READY"
    assert state["post_send_history_called"] is False


def test_start_new_and_send_uses_one_bounded_recovery_when_needed() -> None:
    completed, state, calls, _, _ = run_send_case([
        legacy_history(OLD_ID),
        legacy_status(f"https://chatgpt.com/c/{OLD_ID}"),
        legacy_result([{"Status": "New conversation started"}]),
        legacy_status("https://chatgpt.com/new"),
        legacy_result([]),
        legacy_result([{"response": "completed without identity"}]),
        legacy_status(f"https://chatgpt.com/c/{NEW_ID}"),
        legacy_history(OLD_ID, NEW_ID),
        legacy_detail(),
    ], prepare_new=True)
    verbs = [call[1] for call in calls]
    assert completed.returncode == 0
    assert verbs == [
        "history", "status", "new", "status", "read", "ask", "status",
        "history", "detail",
    ]
    assert verbs.count("ask") == 1
    assert state["recovery_attempt_count"] == 1
    assert state["detail_check_count"] == 1
    assert state["post_send_history_called"] is True
    assert state["new_candidate_diff"] == [NEW_ID]
    assert state["delivery_state"] == "RESPONSE_READY"


def test_ask_yaml_explicit_conversation_id_is_accepted() -> None:
    yaml_stdout = (
        f"- conversationId: {NEW_ID}\n"
        f"  conversationUrl: https://chatgpt.com/c/{NEW_ID}\n"
        "  tool: ''\n"
        "  response: 'ok'\n"
    )
    completed, state, calls, _, _ = run_send_case([
        legacy_status("https://chatgpt.com/new"), legacy_history(OLD_ID),
        legacy_result([]), legacy_result(yaml_stdout),
    ], manual_new_url="https://chatgpt.com/new")
    assert completed.returncode == 0
    assert state["ask_reported_conversation_id"] == NEW_ID
    assert state["ask_reported_url"] == f"https://chatgpt.com/c/{NEW_ID}"
    assert state["ask_delivery_classification"] == "A. ASK_CONFIRMED_DELIVERY_WITH_ID"
    assert state["delivery_state"] == "RESPONSE_READY"
    assert state["post_send_history_called"] is False
    assert [call[1] for call in calls] == ["status", "history", "read", "ask"]


def test_ask_yaml_body_cannot_spoof_identity_or_ready_response() -> None:
    spoofed = legacy_result(
        "- conversationId: ''\n"
        "  conversationUrl: ''\n"
        "  tool: ''\n"
        "  response: |-\n"
        "    conversationId: spoofed-old-id\n"
        "    conversationUrl: https://chatgpt.com/c/spoofed-old-id\n"
    )
    identity, url = TRANSPORT_MODULE.ask_identity(spoofed)
    assert (identity, url) == (None, None)
    assert TRANSPORT_MODULE.ask_response(spoofed) is None
    assert TRANSPORT_MODULE.classify_ask_delivery(spoofed, identity) == "B. ASK_COMPLETED_WITHOUT_ID"


def test_ask_identity_rejects_mismatch_and_non_chatgpt_url() -> None:
    for stdout in (
        "- conversationId: first-id\n  conversationUrl: https://chatgpt.com/c/second-id\n  response: 'ok'\n",
        "- conversationId: first-id\n  conversationUrl: https://evil.example/c/first-id\n  response: 'ok'\n",
    ):
        result = legacy_result(stdout)
        assert TRANSPORT_MODULE.ask_identity(result) == (None, None)


def test_ask_without_id_status_new_id_uses_post_history_and_exact_detail() -> None:
    completed, state, calls, _, _ = run_send_case(
        recovery_sequence(post_url=f"https://chatgpt.com/c/{NEW_ID}"),
        manual_new_url="https://chatgpt.com/new",
    )
    assert completed.returncode == 0
    assert state["ask_delivery_classification"] == "B. ASK_COMPLETED_WITHOUT_ID"
    assert state["post_send_active_conversation_id"] == NEW_ID
    assert state["post_send_page_mode"] == "CONVERSATION"
    assert state["post_send_history_called"] is True
    assert state["new_candidate_diff"] == [NEW_ID]
    assert state["recovery_target_source"] == "POST_SEND_STATUS"
    assert state["detail_check_count"] == 1
    assert [call[1] for call in calls][-3:] == ["status", "history", "detail"]


def test_status_without_id_uses_single_new_history_candidate() -> None:
    completed, state, _, _, _ = run_send_case(
        recovery_sequence(), manual_new_url="https://chatgpt.com/new"
    )
    assert completed.returncode == 0
    assert state["post_send_page_mode"] == "ROOT"
    assert state["new_candidate_diff"] == [NEW_ID]
    assert state["recovery_target_source"] == "POST_SEND_HISTORY_NEW_CANDIDATE_DIFF"
    assert state["actual_delivery_conversation_id"] == NEW_ID


def test_new_history_candidate_requires_both_exact_identifiers() -> None:
    completed, state, _, _, _ = run_send_case(
        recovery_sequence(), manual_new_url="https://chatgpt.com/new"
    )
    assert completed.returncode == 0
    assert state["delivery_state"] == "RESPONSE_READY"
    assert state["detail_check_count"] == 1


def test_new_history_candidate_without_identifiers_stays_unknown() -> None:
    unrelated = legacy_result([{"Role": "user", "Text": "unrelated"}])
    completed, state, _, _, _ = run_send_case(
        recovery_sequence(detail_result=unrelated), manual_new_url="https://chatgpt.com/new"
    )
    assert completed.returncode == 2
    assert state["delivery_state"] == "DELIVERY_UNKNOWN"
    assert state["actual_delivery_conversation_id"] is None


def test_work_item_only_without_message_id_stays_unknown() -> None:
    work_item_only = legacy_result([
        {"Role": "user", "Text": f"WORK_ITEM_ID: {LEGACY_WORK_ITEM}"}
    ])
    completed, state, _, _, _ = run_send_case(
        recovery_sequence(detail_result=work_item_only), manual_new_url="https://chatgpt.com/new"
    )
    assert completed.returncode == 2
    assert state["delivery_state"] == "DELIVERY_UNKNOWN"


def test_message_id_prefix_collision_does_not_match() -> None:
    messages = [{
        "Role": "user",
        "Text": (
            f"WORK_ITEM_ID: {LEGACY_WORK_ITEM}\n"
            f"MESSAGE_ID: {LEGACY_MESSAGE_ID}-OTHER"
        ),
    }]
    assert TRANSPORT_MODULE.inspect_messages(
        messages, LEGACY_WORK_ITEM, LEGACY_MESSAGE_ID
    ) == (False, False, False)


def test_work_item_id_prefix_collision_does_not_match() -> None:
    messages = [{
        "Role": "user",
        "Text": (
            f"WORK_ITEM_ID: {LEGACY_WORK_ITEM}-OTHER\n"
            f"MESSAGE_ID: {LEGACY_MESSAGE_ID}"
        ),
    }]
    assert TRANSPORT_MODULE.inspect_messages(
        messages, LEGACY_WORK_ITEM, LEGACY_MESSAGE_ID
    ) == (False, False, False)


def test_post_send_history_unavailable_uses_status_target_once() -> None:
    unavailable = legacy_result("", returncode=66, stderr="history unavailable")
    completed, state, _, _, _ = run_send_case(
        recovery_sequence(
            post_url=f"https://chatgpt.com/c/{NEW_ID}", post_history=unavailable
        ),
        manual_new_url="https://chatgpt.com/new",
    )
    assert completed.returncode == 0
    assert state["post_send_history_called"] is True
    assert state["post_send_history_available"] is False
    assert state["recovery_target_source"] == "POST_SEND_STATUS"
    assert state["detail_check_count"] == 1


def test_recovery_and_detail_budgets_remain_one() -> None:
    completed, state, calls, _, _ = run_send_case(
        recovery_sequence(detail_result=legacy_result([])),
        manual_new_url="https://chatgpt.com/new",
    )
    assert completed.returncode == 2
    assert state["recovery_attempt_count"] == 1
    assert state["detail_check_count"] == 1
    assert [call[1] for call in calls].count("history") == 2
    assert [call[1] for call in calls].count("detail") == 1


def test_detail_count_only_increments_on_real_invocation() -> None:
    completed, state, calls, _, _ = run_send_case([
        legacy_status(f"https://chatgpt.com/c/{OLD_ID}"), legacy_history(OLD_ID),
        legacy_result([{"Status": "New conversation started"}]),
        legacy_status("https://chatgpt.com/new"), legacy_result([]),
        legacy_result([{"response": "completed without identity"}]),
        legacy_status(f"https://chatgpt.com/c/{NEW_ID}"),
        legacy_history(OLD_ID, NEW_ID),
    ], max_external_commands=8)
    assert completed.returncode == 2
    assert state["external_command_count"] == 8
    assert state["detail_check_count"] == 0
    assert [call[1] for call in calls].count("detail") == 0


def test_multiple_new_history_candidates_stay_unknown_without_detail() -> None:
    completed, state, calls, _, _ = run_send_case(
        recovery_sequence(post_history=legacy_history(OLD_ID, NEW_ID, "second-new")),
        manual_new_url="https://chatgpt.com/new",
    )
    assert completed.returncode == 2
    assert state["delivery_state"] == "DELIVERY_UNKNOWN"
    assert state["new_candidate_diff"] == [NEW_ID, "second-new"]
    assert state["recovery_target_source"] == "AMBIGUOUS_NEW_CANDIDATE_DIFF"
    assert state["detail_check_count"] == 0
    assert [call[1] for call in calls].count("detail") == 0


def test_existing_conversation_recovery_is_not_misroute() -> None:
    sequence = [
        legacy_status(f"https://chatgpt.com/c/{OLD_ID}"), legacy_history(OLD_ID),
        legacy_result([{"response": "completed without identity"}]),
        legacy_status(f"https://chatgpt.com/c/{OLD_ID}"), legacy_history(OLD_ID),
        legacy_detail(),
    ]
    completed, state, _, _, _ = run_send_case(sequence, conversation=OLD_ID)
    assert completed.returncode == 0
    assert state["expected_conversation_mode"] == "EXISTING"
    assert state["delivery_state"] == "RESPONSE_READY"
    assert state["misroute_detected"] is False
    assert state["actual_delivery_conversation_id"] == OLD_ID


def test_prepare_and_send_use_one_shared_read_classifier() -> None:
    source = TRANSPORT.read_text(encoding="utf-8")
    assert "def classify_chatgpt_read_result(" in source
    assert source.count("classification = classify_chatgpt_read_result(") == 2
    real_read = json.loads(REAL_A2P2_EMPTY_RESULT_FIXTURE.read_text(encoding="utf-8"))
    assert TRANSPORT_MODULE.classify_chatgpt_read_result(real_read) == "EMPTY"


def run_manual_read_case(read: dict) -> tuple[subprocess.CompletedProcess[str], dict, list[list[str]]]:
    manual_url = "https://chatgpt.com/new"
    completed, state, calls, _, _ = run_send_case([
        legacy_status(manual_url), legacy_history(), read,
        legacy_result([{"conversationId": NEW_ID, "conversationUrl": f"https://chatgpt.com/c/{NEW_ID}", "response": "ok"}]),
    ], manual_new_url=manual_url)
    return completed, state, calls


def test_send_manual_real_empty_result_sends_once_without_new() -> None:
    real_read = json.loads(REAL_A2P2_EMPTY_RESULT_FIXTURE.read_text(encoding="utf-8"))
    completed, state, calls = run_manual_read_case(real_read)
    verbs = [call[1] for call in calls]
    assert completed.returncode == 0
    assert verbs == ["status", "history", "read", "ask"]
    assert "new" not in verbs
    assert verbs.count("ask") == 1
    assert state["new_command_called"] is False
    assert state["pre_send_already_new"] is True
    assert state["browser_navigation_occurred"] is False
    assert state["read_result"] == "EMPTY"
    assert state["blank_environment_verified"] is True
    assert state["send_attempt_count"] == 1
    assert state["message_send_count"] == 1


def assert_manual_read_blocks(read: dict, expected_result: str, expected_reason: str) -> None:
    completed, state, calls = run_manual_read_case(read)
    verbs = [call[1] for call in calls]
    assert completed.returncode == 2
    assert state["read_result"] == expected_result
    assert state["stop_reason"] == expected_reason
    assert state["send_attempt_count"] == 0
    assert state["message_send_count"] == 0
    assert "ask" not in verbs and "new" not in verbs


def test_send_manual_existing_messages_block_without_send() -> None:
    assert_manual_read_blocks(
        legacy_result([{"Role": "assistant", "Text": "existing"}]),
        "NON_EMPTY", "READ_NOT_EMPTY",
    )


def test_send_manual_unknown_error_blocks_without_send() -> None:
    assert_manual_read_blocks(
        legacy_result("", returncode=66, stderr="ok: false\nerror:\n  code: SELECTOR_FAILED\n"),
        "UNPARSEABLE", "READ_UNPARSEABLE",
    )


def test_send_manual_unparseable_output_blocks_without_send() -> None:
    assert_manual_read_blocks(
        legacy_result("not-json"), "UNPARSEABLE", "READ_UNPARSEABLE"
    )


def test_send_timeout_recovery_regression() -> None:
    completed, state, _, _, _ = run_send_case([
        legacy_status(f"https://chatgpt.com/c/{OLD_ID}"), legacy_history(),
        legacy_result([{"Status": "New conversation started"}]),
        legacy_status("https://chatgpt.com/new"), legacy_result([]),
        legacy_result(returncode=1, timed_out=True),
        legacy_status(f"https://chatgpt.com/c/{NEW_ID}"),
        legacy_history(OLD_ID, NEW_ID), legacy_detail(),
    ])
    assert completed.returncode == 0
    assert state["delivery_state"] == "RESPONSE_READY"
    assert state["recovery_attempt_count"] == 1


def test_send_misroute_regression() -> None:
    completed, state, _, _, _ = run_send_case([
        legacy_status(f"https://chatgpt.com/c/{OLD_ID}"), legacy_history(),
        legacy_result([{"Status": "New conversation started"}]),
        legacy_status("https://chatgpt.com/new"), legacy_result([]),
        legacy_result(returncode=1, stderr="navigated away"),
        legacy_status(f"https://chatgpt.com/c/{OLD_ID}"),
        legacy_history(OLD_ID), legacy_detail(),
    ])
    assert completed.returncode == 2
    assert state["delivery_state"] == "MISROUTED_DELIVERY"
    assert state["official_response_eligible"] is False


def test_visible_schedule_missing_from_agent_count_fails_validation() -> None:
    report = validate_report({
        "WRAPPER_SCHEDULE_CALL_COUNT": 0,
        "AGENT_SCHEDULE_CALL_COUNT": 0,
        "TOTAL_SCHEDULE_CALL_COUNT": 0,
        "VISIBLE_SCHEDULE_TOOL_CALL_EXISTS": True,
        "AGENT_TOOL_TRACE_VERIFICATION": "VERIFIED",
        "IDLE_WAIT_SECONDS": 0,
        "TEST_PROTOCOL_VIOLATION": False,
        "TEST_RESULT": "PASS",
        "EXPERIMENT_ACCEPTANCE": "MET",
    })
    assert report["REPORT_VALIDATION"] == "REPORT_VALIDATION_FAILED"
    assert "VISIBLE_SCHEDULE_NOT_COUNTED" in report["REPORT_VALIDATION_ERRORS"]


def test_wrapper_zero_does_not_replace_agent_schedule_count() -> None:
    report = protocol_report(
        "https://chatgpt.com/c/real-id",
        [
            {"action": "SCHEDULE", "seconds": 1, "initiated_by": "MODEL_INITIATED"},
            {"action": "SCHEDULE", "seconds": 1, "initiated_by": "MODEL_INITIATED"},
        ],
    )
    assert report["WRAPPER_SCHEDULE_CALL_COUNT"] == 0
    assert report["AGENT_SCHEDULE_CALL_COUNT"] == 2
    assert report["TOTAL_SCHEDULE_CALL_COUNT"] == 2
    assert report["TEST_PROTOCOL_VIOLATION"] is True
    assert report["EXPERIMENT_ACCEPTANCE"] == "NOT_MET"


def test_unavailable_agent_trace_does_not_claim_zero_total() -> None:
    state = TRANSPORT_MODULE.prepare_state(
        type("Args", (), {
            "work_item_id": WORK_ITEM,
            "require_existing_conversation": False,
            "max_external_commands": 4,
            "max_experiment_seconds": 60,
            "command_wait_seconds": 15,
        })(),
        Path("synthetic-state.json"),
    )
    assert state["wrapper_schedule_call_count"] == 0
    assert state["agent_schedule_call_count"] is None
    assert state["total_schedule_call_count"] is None
    assert state["agent_tool_trace_verification"] == "UNAVAILABLE"


def test_protocol_violation_cannot_meet_experiment_acceptance() -> None:
    report = validate_report({
        "WRAPPER_SCHEDULE_CALL_COUNT": 0,
        "AGENT_SCHEDULE_CALL_COUNT": 1,
        "TOTAL_SCHEDULE_CALL_COUNT": 1,
        "AGENT_TOOL_TRACE_VERIFICATION": "VERIFIED",
        "IDLE_WAIT_SECONDS": 1,
        "TEST_PROTOCOL_VIOLATION": True,
        "TEST_RESULT": "TEST_PROTOCOL_VIOLATION",
        "EXPERIMENT_ACCEPTANCE": "MET",
    })
    assert report["REPORT_VALIDATION"] == "REPORT_VALIDATION_FAILED"
    assert "PROTOCOL_VIOLATION_CANNOT_MEET_ACCEPTANCE" in report["REPORT_VALIDATION_ERRORS"]


def test_delivery_unknown_report_must_forbid_same_id_resend() -> None:
    report = validate_report({
        "WRAPPER_SCHEDULE_CALL_COUNT": 0,
        "AGENT_SCHEDULE_CALL_COUNT": 0,
        "TOTAL_SCHEDULE_CALL_COUNT": 0,
        "AGENT_TOOL_TRACE_VERIFICATION": "VERIFIED",
        "IDLE_WAIT_SECONDS": 0,
        "TEST_PROTOCOL_VIOLATION": False,
        "TEST_RESULT": "BLOCKED",
        "EXPERIMENT_ACCEPTANCE": "NOT_MET",
        "WRAPPER_DELIVERY_STATE": "DELIVERY_UNKNOWN",
        "SAME_MESSAGE_ID_RESEND_ALLOWED": True,
    })
    assert report["REPORT_VALIDATION"] == "REPORT_VALIDATION_FAILED"
    assert "DELIVERY_UNKNOWN_MUST_FORBID_RESEND" in report["REPORT_VALIDATION_ERRORS"]


def test_report_requires_explicit_agent_trace_fields() -> None:
    report = TRANSPORT_MODULE.validate_experiment_report({"TEST_RESULT": "PASS"})
    assert report["REPORT_VALIDATION_FAILED"] is True
    assert any(
        error.startswith("MISSING_REQUIRED_REPORT_FIELD:")
        for error in report["REPORT_VALIDATION_ERRORS"]
    )


def test_report_rejects_unknown_agent_trace_verification() -> None:
    report = validate_report({"AGENT_TOOL_TRACE_VERIFICATION": "BOGUS"})
    assert report["REPORT_VALIDATION_FAILED"] is True
    assert "INVALID_AGENT_TOOL_TRACE_VERIFICATION" in report["REPORT_VALIDATION_ERRORS"]


def test_send_same_message_id_rejected_regression() -> None:
    completed, _, calls, command, env = run_send_case([
        legacy_history(OLD_ID), legacy_status(f"https://chatgpt.com/c/{OLD_ID}"),
        legacy_result([{"Status": "New conversation started"}]),
        legacy_status("https://chatgpt.com/new"), legacy_result([]),
        legacy_result([{"conversationId": NEW_ID, "conversationUrl": f"https://chatgpt.com/c/{NEW_ID}", "response": "ok"}]),
        legacy_status(f"https://chatgpt.com/c/{NEW_ID}"),
    ], prepare_new=True)
    assert completed.returncode == 0
    repeated = subprocess.run(
        command, capture_output=True, text=True, encoding="utf-8", env=env, check=False
    )
    assert repeated.returncode == 1
    assert "same-ID resend is forbidden" in repeated.stderr
    assert len(calls) == 7


def test_send_external_budget_regression() -> None:
    completed, state, _, _, _ = run_send_case([
        legacy_status(f"https://chatgpt.com/c/{OLD_ID}"), legacy_history(),
        legacy_result([{"Status": "New conversation started"}]),
    ], max_external_commands=3)
    assert completed.returncode == 2
    assert state["send_attempt_count"] == 0
    assert state["external_command_count"] == 3


def main() -> int:
    tests = [
        test_help_exposes_prepare_new,
        test_help_exposes_require_existing_conversation,
        test_old_conversation_to_new_and_empty_result,
        test_real_empty_result_format_regression,
        test_nonzero_exact_empty_result_code_verifies_blank_page,
        test_empty_json_object_or_array_verifies_blank_page,
        test_runtime_contains_required_a2p1_fields,
        test_real_conversation_url_can_execute,
        test_angle_id_placeholder_is_rejected,
        test_chinese_paste_placeholder_is_rejected,
        test_empty_required_value_is_rejected,
        test_placeholder_failure_has_zero_external_commands,
        test_send_placeholder_is_blocked_before_opencli,
        test_synchronous_status_terminates_immediately,
        test_two_second_foreground_trace_is_synchronous,
        test_seven_second_foreground_trace_is_synchronous,
        test_schedule_after_synchronous_result_is_protocol_violation,
        test_background_wait_without_handle_is_rejected,
        test_bound_background_result_is_read_once_within_fifteen_seconds,
        test_background_completion_is_not_synchronous_completion,
        test_schedule_call_cannot_report_zero_wait,
        test_protocol_violation_cannot_return_pass,
        test_contradictory_report_fails_validation,
        test_unauthorized_sleep_is_protocol_violation,
        test_poll_requires_authorized_running_job,
        test_all_experiment_actions_are_counted,
        test_old_conversation_still_active_fails,
        test_existing_messages_fail,
        test_unknown_error_code_is_unparseable,
        test_unparseable_output_blocks_before_send,
        test_already_new_reports_no_conversation_transition,
        test_required_existing_from_new_stops_before_new,
        test_required_existing_from_root_stops_before_new,
        test_required_existing_rejects_invalid_conversation_url,
        test_prepare_without_requirement_remains_compatible,
        test_old_conversation_reports_verified_transition,
        test_all_read_failures_remain_zero_send,
        test_sixty_second_budget_is_machine_enforced,
        test_prepare_never_calls_ask_or_send,
        test_external_command_budget_stops_before_next_command,
        test_send_correct_new_conversation_regression,
        test_send_help_exposes_integrated_prepare_new,
        test_start_new_and_send_completes_in_one_wrapper_call,
        test_start_new_and_send_uses_one_bounded_recovery_when_needed,
        test_ask_yaml_explicit_conversation_id_is_accepted,
        test_ask_yaml_body_cannot_spoof_identity_or_ready_response,
        test_ask_identity_rejects_mismatch_and_non_chatgpt_url,
        test_ask_without_id_status_new_id_uses_post_history_and_exact_detail,
        test_status_without_id_uses_single_new_history_candidate,
        test_new_history_candidate_requires_both_exact_identifiers,
        test_new_history_candidate_without_identifiers_stays_unknown,
        test_work_item_only_without_message_id_stays_unknown,
        test_message_id_prefix_collision_does_not_match,
        test_work_item_id_prefix_collision_does_not_match,
        test_post_send_history_unavailable_uses_status_target_once,
        test_recovery_and_detail_budgets_remain_one,
        test_detail_count_only_increments_on_real_invocation,
        test_multiple_new_history_candidates_stay_unknown_without_detail,
        test_existing_conversation_recovery_is_not_misroute,
        test_prepare_and_send_use_one_shared_read_classifier,
        test_send_manual_real_empty_result_sends_once_without_new,
        test_send_manual_existing_messages_block_without_send,
        test_send_manual_unknown_error_blocks_without_send,
        test_send_manual_unparseable_output_blocks_without_send,
        test_send_timeout_recovery_regression,
        test_send_misroute_regression,
        test_visible_schedule_missing_from_agent_count_fails_validation,
        test_wrapper_zero_does_not_replace_agent_schedule_count,
        test_unavailable_agent_trace_does_not_claim_zero_total,
        test_protocol_violation_cannot_meet_experiment_acceptance,
        test_delivery_unknown_report_must_forbid_same_id_resend,
        test_report_requires_explicit_agent_trace_fields,
        test_report_rejects_unknown_agent_trace_verification,
        test_send_same_message_id_rejected_regression,
        test_send_external_budget_regression,
    ]
    for test in tests:
        test()
        print(f"PASS: {test.__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
