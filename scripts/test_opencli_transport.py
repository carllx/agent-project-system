"""Pure-local public-CLI tests for the RR Lead OpenCLI transport."""

from __future__ import annotations

import hashlib
import json
import importlib.util
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TRANSPORT = ROOT / "skills" / "research-review-lead" / "scripts" / "opencli_transport.py"
EXPERIMENT_PROTOCOL = (
    ROOT / "skills" / "research-review-lead" / "scripts" / "experiment_protocol.py"
)
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
time.sleep(3 if item.get("timed_out") else item.get("sleep", 0))
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


def test_experiment_protocol_module_is_loadable() -> None:
    spec = importlib.util.spec_from_file_location(
        "rr_experiment_protocol_direct_test", EXPERIMENT_PROTOCOL
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.unresolved_required_values({"target": "TODO"}) == ["target"]


def test_opencli_transport_reexports_protocol_api() -> None:
    for name in (
        "unresolved_required_values",
        "assess_experiment_protocol",
        "validate_experiment_report",
    ):
        exported = getattr(TRANSPORT_MODULE, name)
        assert callable(exported)
        assert Path(exported.__code__.co_filename).resolve() == EXPERIMENT_PROTOCOL.resolve()


def test_direct_opencli_transport_help_still_works() -> None:
    completed = subprocess.run(
        [sys.executable, str(TRANSPORT), "--help"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert "prepare-new" in completed.stdout


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


def rr_review_text(
    *, work_item_id: str = LEGACY_WORK_ITEM,
    message_id: str = LEGACY_MESSAGE_ID,
    round_value: str = "0",
    omit: str | None = None,
    reply_field: str = "IN_REPLY_TO_MESSAGE_ID",
    extra_fields: tuple[tuple[str, str], ...] = (),
) -> str:
    values = {
        "WORK_ITEM_ID": work_item_id,
        reply_field: message_id,
        "ROUND": round_value,
        "REVIEW_DECISION": "PASS",
        "WORK_ITEM_STATE": "ACHIEVED",
        "ACCEPTANCE_STATUS": "all criteria MET",
        "FINDINGS": "None.",
        "BLOCKERS": "None.",
        "DEBT": "None.",
        "NEXT_WORK_ORDER": "None.",
        "VALIDATION": "Pure-local fixture.",
        "USER_DECISION_REQUIRED": "false",
    }
    fields = "\n".join(
        f"{name}: {value}" for name, value in values.items() if name != omit
    )
    if extra_fields:
        fields += "\n" + "\n".join(f"{name}: {value}" for name, value in extra_fields)
    return f"RR_REVIEW_BEGIN\n{fields}\nRR_REVIEW_END"


def legacy_detail(ready: bool = True) -> dict:
    messages = [{"Role": "user", "Text": f"WORK_ITEM_ID: {LEGACY_WORK_ITEM}\nMESSAGE_ID: {LEGACY_MESSAGE_ID}\nROUND: 0"}]
    if ready:
        messages.append({"Role": "assistant", "Text": rr_review_text(), "Generating": False, "StableSeconds": 3})
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


def opencli_timeout_result() -> dict:
    return legacy_result(
        returncode=75,
        stderr=(
            "ok: false\nerror:\n  code: TIMEOUT\n"
            "  message: chatgpt ask timed out after 120s\n  exitCode: 75\n"
        ),
    )


def timeout_then_recover_sequence(detail_result: dict) -> list[dict]:
    return [
        legacy_status("https://chatgpt.com/new"),
        legacy_history(OLD_ID),
        legacy_result([]),
        opencli_timeout_result(),
        legacy_status(f"https://chatgpt.com/c/{NEW_ID}"),
        legacy_history(OLD_ID, NEW_ID),
        detail_result,
    ]


def run_recover(
    command: list[str], env: dict[str, str]
) -> tuple[subprocess.CompletedProcess[str], dict, list[list[str]]]:
    state_path = Path(command[command.index("--state-file") + 1])
    completed = subprocess.run(
        [sys.executable, str(TRANSPORT), "recover", "--state-file", str(state_path)],
        capture_output=True, text=True, encoding="utf-8", env=env, check=False,
    )
    state = json.loads(state_path.read_text(encoding="utf-8"))
    log = Path(env["OPENCLI_FAKE_LOG"])
    calls = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    return completed, state, calls


def run_pending_resume(
    command: list[str], env: dict[str, str]
) -> tuple[subprocess.CompletedProcess[str], dict, list[list[str]]]:
    state_path = Path(command[command.index("--state-file") + 1])
    completed = subprocess.run(
        [
            sys.executable,
            str(TRANSPORT),
            "recover",
            "--state-file",
            str(state_path),
            "--continue-pending",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        check=False,
    )
    state = json.loads(state_path.read_text(encoding="utf-8"))
    log = Path(env["OPENCLI_FAKE_LOG"])
    calls = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    return completed, state, calls


def pending_resume_case(
    continuation_results: list[dict],
) -> tuple[list[str], dict[str, str], dict]:
    sequence = timeout_then_recover_sequence(legacy_detail(False)) + continuation_results
    _, _, _, command, env = run_send_case(
        sequence, manual_new_url="https://chatgpt.com/new"
    )
    _, pending, _ = run_recover(command, env)
    assert pending["delivery_state"] == "RESPONSE_PENDING"
    return command, env, pending


def process_exists(pid: int) -> bool:
    if os.name == "nt":
        import ctypes

        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        exit_code = ctypes.c_ulong()
        queried = ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
        ctypes.windll.kernel32.CloseHandle(handle)
        return bool(queried and exit_code.value == 259)
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def test_ask_hard_timeout_returns_before_global_budget() -> None:
    root = Path(tempfile.mkdtemp(prefix="rr-ask-hard-timeout-"))
    fake = root / "hanging_opencli.py"
    child_pid = root / "child.pid"
    fake.write_text(
        "import pathlib, subprocess, sys, time\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])\n"
        "pathlib.Path(sys.argv[1]).write_text(str(child.pid), encoding='utf-8')\n"
        "time.sleep(30)\n",
        encoding="utf-8",
    )
    previous = os.environ.get("OPENCLI_TRANSPORT_EXECUTABLE")
    os.environ["OPENCLI_TRANSPORT_EXECUTABLE"] = str(fake)
    started = time.monotonic()
    try:
        result = TRANSPORT_MODULE.run_opencli([str(child_pid)], 0.5)
    finally:
        if previous is None:
            os.environ.pop("OPENCLI_TRANSPORT_EXECUTABLE", None)
        else:
            os.environ["OPENCLI_TRANSPORT_EXECUTABLE"] = previous
    elapsed = time.monotonic() - started
    assert result["timed_out"] is True
    assert result["process_tree_terminated"] is True
    assert elapsed < 5, elapsed
    assert elapsed < TRANSPORT_MODULE.MAX_EXPERIMENT_SECONDS
    assert child_pid.is_file()
    assert not process_exists(int(child_pid.read_text(encoding="utf-8")))


def test_ask_timeout_preserves_recovery_budget() -> None:
    completed, state, calls, _, _ = run_send_case(
        timeout_then_recover_sequence(legacy_detail()),
        manual_new_url="https://chatgpt.com/new",
    )
    assert completed.returncode == 2
    assert state["ask_timed_out"] is True
    assert state["recovery_attempt_count"] == 0
    assert state["detail_check_count"] == 0
    assert state["external_command_count"] < state["parameters"]["max_external_commands"]
    assert [call[1] for call in calls] == ["status", "history", "read", "ask"]


def test_timeout_does_not_mark_message_as_not_sent() -> None:
    _, state, _, _, _ = run_send_case(
        timeout_then_recover_sequence(legacy_detail()),
        manual_new_url="https://chatgpt.com/new",
    )
    assert state["delivery_state"] == "DELIVERY_UNKNOWN"
    assert state["send_attempt_count"] == 1
    assert state["message_send_count"] == 1


def test_timeout_forbids_same_message_id_resend() -> None:
    _, _, calls, command, env = run_send_case(
        timeout_then_recover_sequence(legacy_detail()),
        manual_new_url="https://chatgpt.com/new",
    )
    repeated = subprocess.run(
        command, capture_output=True, text=True, encoding="utf-8", env=env, check=False,
    )
    assert repeated.returncode == 1
    assert "same-ID resend is forbidden" in repeated.stderr
    assert sum(call[1] == "ask" for call in calls) == 1


def test_recover_never_invokes_ask_or_send() -> None:
    _, _, _, command, env = run_send_case(
        timeout_then_recover_sequence(legacy_detail(False)),
        manual_new_url="https://chatgpt.com/new",
    )
    completed, _, calls = run_recover(command, env)
    assert completed.returncode == 2
    recovery_verbs = [call[1] for call in calls[4:]]
    assert recovery_verbs == ["status", "history", "detail"]
    assert "ask" not in recovery_verbs and "send" not in recovery_verbs


def test_recover_can_bind_conversation_after_ask_timeout() -> None:
    _, _, _, command, env = run_send_case(
        timeout_then_recover_sequence(legacy_detail(False)),
        manual_new_url="https://chatgpt.com/new",
    )
    _, state, _ = run_recover(command, env)
    assert state["actual_delivery_conversation_id"] == NEW_ID
    assert state["verified_target_conversation_id"] == NEW_ID
    assert state["response_source_conversation_id"] == NEW_ID


def test_recover_pending_response_preserves_conversation_id() -> None:
    _, _, _, command, env = run_send_case(
        timeout_then_recover_sequence(legacy_detail(False)),
        manual_new_url="https://chatgpt.com/new",
    )
    _, state, _ = run_recover(command, env)
    assert state["delivery_state"] == "RESPONSE_PENDING"
    assert state["response_identity_status"] == "RESPONSE_PENDING"
    assert state["verified_target_conversation_id"] == NEW_ID
    assert state["official_response_eligible"] is False


def test_recover_accepts_later_identity_bound_rr_review() -> None:
    _, _, _, command, env = run_send_case(
        timeout_then_recover_sequence(legacy_detail()),
        manual_new_url="https://chatgpt.com/new",
    )
    completed, state, _ = run_recover(command, env)
    assert completed.returncode == 0
    assert state["delivery_state"] == "RESPONSE_READY"
    assert state["response_identity_status"] == "RESPONSE_IDENTITY_VERIFIED"
    assert state["official_response_eligible"] is True


def test_manual_recover_uses_fresh_operation_budget() -> None:
    _, state, _, command, env = run_send_case(
        timeout_then_recover_sequence(legacy_detail()),
        manual_new_url="https://chatgpt.com/new",
    )
    state_path = Path(command[command.index("--state-file") + 1])
    state["started_at"] = "2000-01-01T00:00:00+00:00"
    state["current_operation_started_at"] = state["started_at"]
    state["external_command_count"] = state["parameters"]["max_external_commands"]
    state_path.write_text(json.dumps(state), encoding="utf-8")
    completed, recovered, calls = run_recover(command, env)
    assert completed.returncode == 0
    assert recovered["current_operation"] == "MANUAL_RECOVER"
    assert recovered["current_operation_started_at"] == recovered["manual_recover_started_at"]
    assert recovered["current_operation_external_command_count"] == 3
    assert [call[1] for call in calls[4:]] == ["status", "history", "detail"]


def test_manual_recover_preserves_original_send_started_at() -> None:
    _, state, _, command, env = run_send_case(
        timeout_then_recover_sequence(legacy_detail()),
        manual_new_url="https://chatgpt.com/new",
    )
    state_path = Path(command[command.index("--state-file") + 1])
    original = state["original_send_started_at"]
    state["started_at"] = "2000-01-01T00:00:00+00:00"
    state_path.write_text(json.dumps(state), encoding="utf-8")
    _, recovered, _ = run_recover(command, env)
    assert recovered["original_send_started_at"] == original
    assert recovered["manual_recover_started_at"] == recovered["current_operation_started_at"]


def test_pending_response_can_resume_in_new_invocation() -> None:
    command, env, _ = pending_resume_case([legacy_detail()])
    completed, state, _ = run_pending_resume(command, env)
    assert completed.returncode == 0
    assert state["pending_response_continuation_count"] == 1
    assert state["delivery_state"] == "RESPONSE_READY"


def test_pending_resume_uses_fresh_operation_budget() -> None:
    command, env, state = pending_resume_case([legacy_detail()])
    state_path = Path(command[command.index("--state-file") + 1])
    state["current_operation_started_at"] = "2000-01-01T00:00:00+00:00"
    state["external_command_count"] = state["parameters"]["max_external_commands"]
    state_path.write_text(json.dumps(state), encoding="utf-8")
    completed, resumed, _ = run_pending_resume(command, env)
    assert completed.returncode == 0
    assert resumed["current_operation"] == "PENDING_RESPONSE_CONTINUATION"
    assert resumed["current_operation_external_command_count"] == 1
    assert resumed["pending_response_last_checked_at"] == resumed["current_operation_started_at"]


def test_pending_resume_never_invokes_ask_send_or_new() -> None:
    command, env, _ = pending_resume_case([legacy_detail()])
    _, _, calls = run_pending_resume(command, env)
    continuation_verbs = [call[1] for call in calls[7:]]
    assert continuation_verbs == ["detail"]
    assert not {"ask", "send", "new"}.intersection(continuation_verbs)


def test_pending_resume_does_not_change_send_count() -> None:
    command, env, pending = pending_resume_case([legacy_detail()])
    before = (pending["send_attempt_count"], pending["message_send_count"])
    _, resumed, _ = run_pending_resume(command, env)
    assert (resumed["send_attempt_count"], resumed["message_send_count"]) == before


def test_pending_resume_requires_saved_conversation() -> None:
    command, env, state = pending_resume_case([])
    state_path = Path(command[command.index("--state-file") + 1])
    state["verified_target_conversation_id"] = None
    state_path.write_text(json.dumps(state), encoding="utf-8")
    completed, _, calls = run_pending_resume(command, env)
    assert completed.returncode == 1
    assert "saved identity" in completed.stderr
    assert len(calls) == 7


def test_pending_resume_preserves_message_identity() -> None:
    command, env, pending = pending_resume_case([legacy_detail()])
    _, resumed, _ = run_pending_resume(command, env)
    assert resumed["work_item_id"] == pending["work_item_id"]
    assert resumed["message_id"] == pending["message_id"]
    assert resumed["original_send_started_at"] == pending["original_send_started_at"]


def test_pending_resume_remains_pending_for_incomplete_reply() -> None:
    incomplete = legacy_detail(False)
    command, env, _ = pending_resume_case([
        incomplete,
        legacy_status(f"https://chatgpt.com/c/{NEW_ID}"),
        incomplete,
    ])
    completed, state, calls = run_pending_resume(command, env)
    assert completed.returncode == 2
    assert state["delivery_state"] == "RESPONSE_PENDING"
    assert state["pending_response_last_result"] == "RESPONSE_PENDING"
    assert [call[1] for call in calls[7:]] == ["detail", "status", "read"]


def test_pending_resume_accepts_later_complete_rr_review() -> None:
    command, env, _ = pending_resume_case([legacy_detail()])
    _, state, _ = run_pending_resume(command, env)
    assert state["response_identity_status"] == "RESPONSE_IDENTITY_VERIFIED"
    assert state["official_response_eligible"] is True
    assert state["pending_response_last_result"] == "RESPONSE_READY"


def test_pending_resume_rejects_wrong_reply_identity() -> None:
    wrong = legacy_detail(False)
    wrong["stdout"] = json.dumps([
        {"Role": "user", "Text": f"WORK_ITEM_ID: {LEGACY_WORK_ITEM}\nMESSAGE_ID: {LEGACY_MESSAGE_ID}\nROUND: 0"},
        {"Role": "assistant", "Text": rr_review_text(message_id=f"{LEGACY_MESSAGE_ID}-WRONG"), "Generating": False, "StableSeconds": 3},
    ])
    command, env, _ = pending_resume_case([wrong])
    completed, state, _ = run_pending_resume(command, env)
    assert completed.returncode == 2
    assert state["delivery_state"] == "RESPONSE_IDENTITY_REJECTED"
    assert state["response_identity_status"] == "RESPONSE_IDENTITY_REJECTED"
    assert state["pending_response_last_identity_status"] == "RESPONSE_IDENTITY_MISMATCH"
    assert state["pending_response_last_result"] == "RESPONSE_IDENTITY_REJECTED"
    assert state["official_response_eligible"] is False


def test_pending_resume_stops_at_configured_limit() -> None:
    incomplete = legacy_detail(False)
    command, env, state = pending_resume_case([
        incomplete,
        legacy_status(f"https://chatgpt.com/c/{NEW_ID}"),
        incomplete,
    ])
    state_path = Path(command[command.index("--state-file") + 1])
    state["parameters"]["max_pending_response_continuations"] = 1
    state_path.write_text(json.dumps(state), encoding="utf-8")
    completed, resumed, _ = run_pending_resume(command, env)
    assert completed.returncode == 2
    assert resumed["delivery_state"] == "BLOCKED_RESPONSE_TIMEOUT"
    assert resumed["pending_response_continuation_count"] == 1
    assert resumed["pending_response_last_result"] == "BLOCKED_RESPONSE_TIMEOUT"
    assert TRANSPORT_MODULE.MAX_PENDING_RESPONSE_CONTINUATIONS == 3


def test_compact_packet_payload_is_single_line_and_lossless() -> None:
    body = (
        'SHARED_OBJECTIVE: preserve 中文, "quotes", and \\backslashes\n'
        "EVIDENCE: line one\nline two"
    )
    args = type("Args", (), {
        "work_item_id": LEGACY_WORK_ITEM,
        "message_id": LEGACY_MESSAGE_ID,
        "round": 0,
        "message_type": "EVIDENCE_PACKET",
    })()
    payload = TRANSPORT_MODULE.prepare_payload(args, body)
    packet = json.loads(payload)
    assert payload.splitlines() == [payload]
    assert packet["WORK_ITEM_ID"] == LEGACY_WORK_ITEM
    assert packet["MESSAGE_ID"] == LEGACY_MESSAGE_ID
    assert packet["ROUND"] == 0
    assert packet["MESSAGE_TYPE"] == "EVIDENCE_PACKET"
    assert packet["EVIDENCE"] == body
    assert packet["END_SENTINEL"] == f"RR-PACKET-COMPLETE:{LEGACY_MESSAGE_ID}"
    assert {
        "SHARED_OBJECTIVE", "ACCEPTANCE_CRITERIA", "RR_LEAD_QUESTION"
    } <= packet.keys()


def test_compact_packet_identity_is_accepted_with_formatter_suffix() -> None:
    text = json.dumps({
        "WORK_ITEM_ID": LEGACY_WORK_ITEM,
        "MESSAGE_ID": LEGACY_MESSAGE_ID,
    }, separators=(",", ":")) + "\nShow more"
    found, replied, stable = TRANSPORT_MODULE.inspect_messages(
        [{"Role": "user", "Text": text}], LEGACY_WORK_ITEM, LEGACY_MESSAGE_ID
    )
    assert (found, replied, stable) == (True, False, False)


def test_compact_packet_wrong_identity_is_rejected() -> None:
    text = json.dumps({
        "WORK_ITEM_ID": LEGACY_WORK_ITEM,
        "MESSAGE_ID": f"{LEGACY_MESSAGE_ID}-OTHER",
    }, separators=(",", ":"))
    found, _, _ = TRANSPORT_MODULE.inspect_messages(
        [{"Role": "user", "Text": text}], LEGACY_WORK_ITEM, LEGACY_MESSAGE_ID
    )
    assert found is False


def test_send_passes_one_complete_single_line_packet_to_opencli() -> None:
    _, state, calls, _, _ = run_send_case(
        timeout_then_recover_sequence(legacy_detail()),
        manual_new_url="https://chatgpt.com/new",
    )
    ask_call = next(call for call in calls if call[1] == "ask")
    payload = ask_call[2]
    packet = json.loads(payload)
    assert payload.splitlines() == [payload]
    assert packet["WORK_ITEM_ID"] == LEGACY_WORK_ITEM
    assert packet["MESSAGE_ID"] == LEGACY_MESSAGE_ID
    assert packet["EVIDENCE"] == "synthetic body"
    assert packet["END_SENTINEL"] == f"RR-PACKET-COMPLETE:{LEGACY_MESSAGE_ID}"
    assert state["payload_integrity"] == {
        "transport_method": "argv",
        "byte_length": len(payload.encode("utf-8")),
        "character_length": len(payload),
        "line_count": 1,
        "sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        "has_work_item_id": True,
        "has_message_id": True,
        "has_end_sentinel": True,
    }


def test_manual_recover_has_independent_attempt_budget() -> None:
    _, state, _, command, env = run_send_case(
        timeout_then_recover_sequence(legacy_detail()),
        manual_new_url="https://chatgpt.com/new",
    )
    state_path = Path(command[command.index("--state-file") + 1])
    state["automatic_recovery_attempt_count"] = 1
    state["recovery_attempt_count"] = 1
    state_path.write_text(json.dumps(state), encoding="utf-8")
    completed, recovered, _ = run_recover(command, env)
    assert completed.returncode == 0
    assert recovered["automatic_recovery_attempt_count"] == 1
    assert recovered["manual_recovery_attempt_count"] == 1
    assert recovered["recovery_attempt_count"] == 2


def test_manual_recover_never_invokes_ask_send_or_new() -> None:
    _, _, _, command, env = run_send_case(
        timeout_then_recover_sequence(legacy_detail(False)),
        manual_new_url="https://chatgpt.com/new",
    )
    _, _, calls = run_recover(command, env)
    recovery_verbs = [call[1] for call in calls[4:]]
    assert recovery_verbs == ["status", "history", "detail"]
    assert not {"ask", "send", "new"}.intersection(recovery_verbs)


def test_manual_recover_does_not_change_send_count() -> None:
    _, state, _, command, env = run_send_case(
        timeout_then_recover_sequence(legacy_detail()),
        manual_new_url="https://chatgpt.com/new",
    )
    before = (state["send_attempt_count"], state["message_send_count"])
    _, recovered, _ = run_recover(command, env)
    assert (recovered["send_attempt_count"], recovered["message_send_count"]) == before


def test_empty_status_does_not_erase_candidate_conversation_id() -> None:
    sequence = timeout_then_recover_sequence(legacy_detail())
    sequence[4] = legacy_status("https://chatgpt.com/")
    _, state, _, command, env = run_send_case(
        sequence, manual_new_url="https://chatgpt.com/new",
    )
    state_path = Path(command[command.index("--state-file") + 1])
    state["candidate_conversation_id"] = NEW_ID
    state["post_send_active_conversation_id"] = NEW_ID
    state_path.write_text(json.dumps(state), encoding="utf-8")
    _, recovered, _ = run_recover(command, env)
    assert recovered["last_observed_status_conversation_id"] is None
    assert recovered["candidate_conversation_id"] == NEW_ID
    assert recovered["post_send_active_conversation_id"] == NEW_ID


def test_conflicting_candidate_is_not_silently_overwritten() -> None:
    state = {
        "candidate_conversation_id": "candidate-a",
        "candidate_conversation_conflicts": [],
    }
    TRANSPORT_MODULE.observe_candidate(state, "candidate-b", "STATUS_PROBE")
    assert state["candidate_conversation_id"] == "candidate-a"
    assert state["candidate_conversation_conflict"] is True
    assert state["candidate_conversation_conflicts"] == [{
        "preserved_conversation_id": "candidate-a",
        "observed_conversation_id": "candidate-b",
        "source": "STATUS_PROBE",
        "at": state["candidate_conversation_conflicts"][0]["at"],
    }]


def test_candidate_is_not_verified_target() -> None:
    state = {
        "candidate_conversation_id": None,
        "verified_target_conversation_id": None,
        "official_response_eligible": False,
    }
    TRANSPORT_MODULE.observe_candidate(state, NEW_ID, "STATUS_PROBE")
    assert state["candidate_conversation_id"] == NEW_ID
    assert state["verified_target_conversation_id"] is None
    assert state["official_response_eligible"] is False


def test_exact_detail_promotes_candidate_to_verified_target() -> None:
    sequence = timeout_then_recover_sequence(legacy_detail())
    sequence[4] = legacy_status("https://chatgpt.com/")
    _, state, _, command, env = run_send_case(
        sequence, manual_new_url="https://chatgpt.com/new",
    )
    state_path = Path(command[command.index("--state-file") + 1])
    state["candidate_conversation_id"] = NEW_ID
    state_path.write_text(json.dumps(state), encoding="utf-8")
    completed, recovered, _ = run_recover(command, env)
    assert completed.returncode == 0
    assert recovered["verified_target_conversation_id"] == NEW_ID
    assert recovered["response_source_conversation_id"] == NEW_ID
    assert recovered["official_response_eligible"] is True


def test_old_timeout_state_can_run_one_manual_recover() -> None:
    sequence = timeout_then_recover_sequence(legacy_detail())
    sequence[4] = legacy_status("https://chatgpt.com/")
    _, state, _, command, env = run_send_case(
        sequence, manual_new_url="https://chatgpt.com/new",
    )
    state_path = Path(command[command.index("--state-file") + 1])
    raw_path = state_path.parent / "raw" / "legacy-status-after-send.json"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(json.dumps(legacy_status(f"https://chatgpt.com/c/{NEW_ID}")), encoding="utf-8")
    state["raw_outputs"].append(str(raw_path))
    for field in (
        "automatic_recovery_attempt_count",
        "manual_recovery_attempt_count",
        "manual_recover_started_at",
        "candidate_conversation_id",
        "candidate_conversation_source",
        "current_operation",
        "current_operation_started_at",
        "current_operation_external_command_count",
        "original_send_started_at",
    ):
        state.pop(field, None)
    state["started_at"] = "2000-01-01T00:00:00+00:00"
    state["external_command_count"] = state["parameters"]["max_external_commands"]
    state["recovery_attempt_count"] = 1
    state_path.write_text(json.dumps(state), encoding="utf-8")
    first, recovered, calls = run_recover(command, env)
    assert first.returncode == 0
    assert recovered["candidate_conversation_id"] == NEW_ID
    assert recovered["verified_target_conversation_id"] == NEW_ID
    assert recovered["manual_recovery_attempt_count"] == 1
    first_call_count = len(calls)
    _, repeated, repeated_calls = run_recover(command, env)
    assert repeated["manual_recovery_attempt_count"] == 1
    assert len(repeated_calls) == first_call_count


def test_send_correct_new_conversation_regression() -> None:
    completed, state, _, _, _ = run_send_case([
        legacy_status(f"https://chatgpt.com/c/{OLD_ID}"), legacy_history(),
        legacy_result([{"Status": "New conversation started"}]),
        legacy_status("https://chatgpt.com/new"), legacy_result([]),
        legacy_result([{"conversationId": NEW_ID, "conversationUrl": f"https://chatgpt.com/c/{NEW_ID}", "response": rr_review_text()}]),
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
            "response": rr_review_text(),
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
    assert state["official_response_eligible"] is True
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
    assert completed.returncode == 2
    assert state["ask_reported_conversation_id"] == NEW_ID
    assert state["ask_reported_url"] == f"https://chatgpt.com/c/{NEW_ID}"
    assert state["ask_delivery_classification"] == "A. ASK_CONFIRMED_DELIVERY_WITH_ID"
    assert state["delivery_state"] == "RESPONSE_IDENTITY_MISSING"
    assert state["official_response_eligible"] is False
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
        legacy_result([{"conversationId": NEW_ID, "conversationUrl": f"https://chatgpt.com/c/{NEW_ID}", "response": rr_review_text()}]),
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
    sent, state, _, command, env = run_send_case([
        legacy_status(f"https://chatgpt.com/c/{OLD_ID}"), legacy_history(),
        legacy_result([{"Status": "New conversation started"}]),
        legacy_status("https://chatgpt.com/new"), legacy_result([]),
        legacy_result(returncode=1, timed_out=True),
        legacy_status(f"https://chatgpt.com/c/{NEW_ID}"),
        legacy_history(OLD_ID, NEW_ID), legacy_detail(),
    ])
    assert sent.returncode == 2
    assert state["delivery_state"] == "DELIVERY_UNKNOWN"
    assert state["recovery_attempt_count"] == 0
    recovered, state, _ = run_recover(command, env)
    assert recovered.returncode == 0
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
        legacy_result([{"conversationId": NEW_ID, "conversationUrl": f"https://chatgpt.com/c/{NEW_ID}", "response": rr_review_text()}]),
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


def rr_identity_result(
    assistant_texts: list[str], *, source: str = NEW_ID,
    user_text: str | None = None,
) -> dict:
    messages = [{
        "Role": "user",
        "Text": user_text or (
            f"WORK_ITEM_ID: {LEGACY_WORK_ITEM}\n"
            f"MESSAGE_ID: {LEGACY_MESSAGE_ID}\nROUND: 0"
        ),
    }]
    messages.extend({
        "Role": "assistant", "Text": text, "Generating": False, "StableSeconds": 3,
    } for text in assistant_texts)
    return TRANSPORT_MODULE.verify_rr_response_identity(
        messages, source, NEW_ID, LEGACY_WORK_ITEM, LEGACY_MESSAGE_ID, 0
    )


def test_rr_response_exact_identity_is_accepted() -> None:
    result = rr_identity_result([rr_review_text()])
    assert result["status"] == "RESPONSE_IDENTITY_VERIFIED"
    assert result["review"]["IN_REPLY_TO_MESSAGE_ID"] == LEGACY_MESSAGE_ID


def test_canonical_in_reply_to_message_id_is_accepted() -> None:
    result = rr_identity_result([rr_review_text()])
    assert result["status"] == "RESPONSE_IDENTITY_VERIFIED"
    assert result["review"]["IN_REPLY_TO_MESSAGE_ID"] == LEGACY_MESSAGE_ID
    assert result["review"]["REPLY_ID_SOURCE"] == "CANONICAL"


def test_exact_legacy_reply_to_message_id_is_normalized() -> None:
    result = rr_identity_result([rr_review_text(reply_field="REPLY_TO_MESSAGE_ID")])
    assert result["status"] == "RESPONSE_IDENTITY_VERIFIED"
    assert result["review"]["IN_REPLY_TO_MESSAGE_ID"] == LEGACY_MESSAGE_ID
    assert result["review"]["REPLY_ID_SOURCE"] == "LEGACY_ALIAS"
    assert "REPLY_TO_MESSAGE_ID" not in result["review"]


def test_legacy_alias_wrong_message_id_is_rejected() -> None:
    result = rr_identity_result([rr_review_text(
        message_id=f"{LEGACY_MESSAGE_ID}-OTHER", reply_field="REPLY_TO_MESSAGE_ID",
    )])
    assert result["status"] == "RESPONSE_IDENTITY_REJECTED"


def test_canonical_and_alias_same_value_are_accepted() -> None:
    result = rr_identity_result([rr_review_text(
        extra_fields=(("REPLY_TO_MESSAGE_ID", LEGACY_MESSAGE_ID),),
    )])
    assert result["status"] == "RESPONSE_IDENTITY_VERIFIED"
    assert result["review"]["IN_REPLY_TO_MESSAGE_ID"] == LEGACY_MESSAGE_ID
    assert result["review"]["REPLY_ID_SOURCE"] == "CANONICAL"


def test_canonical_and_alias_conflict_is_rejected() -> None:
    result = rr_identity_result([rr_review_text(
        extra_fields=(("REPLY_TO_MESSAGE_ID", f"{LEGACY_MESSAGE_ID}-OTHER"),),
    )])
    assert result["status"] == "RESPONSE_IDENTITY_REJECTED"


def test_duplicate_legacy_alias_is_rejected() -> None:
    result = rr_identity_result([rr_review_text(
        reply_field="REPLY_TO_MESSAGE_ID",
        extra_fields=(("REPLY_TO_MESSAGE_ID", LEGACY_MESSAGE_ID),),
    )])
    assert result["status"] == "RESPONSE_IDENTITY_REJECTED"


def test_missing_reply_identity_fields_is_rejected() -> None:
    result = rr_identity_result([rr_review_text(omit="IN_REPLY_TO_MESSAGE_ID")])
    assert result["status"] == "RESPONSE_IDENTITY_REJECTED"


def test_legacy_alias_does_not_bypass_rr_envelope_validation() -> None:
    text = "leading text\n" + rr_review_text(reply_field="REPLY_TO_MESSAGE_ID")
    result = rr_identity_result([text])
    assert result["status"] == "RESPONSE_IDENTITY_MISSING"
    assert result["review"] is None


def test_optional_response_message_metadata_does_not_contaminate_fields() -> None:
    result = rr_identity_result([rr_review_text(extra_fields=(
        ("MESSAGE_ID", f"{LEGACY_WORK_ITEM}-R0-REVIEW"),
        ("MESSAGE_TYPE", "RR_REVIEW"),
    ))])
    assert result["status"] == "RESPONSE_IDENTITY_VERIFIED"
    assert result["review"]["WORK_ITEM_ID"] == LEGACY_WORK_ITEM
    assert result["review"]["ROUND"] == "0"


def test_exact_response_message_id_is_accepted() -> None:
    value = f"{LEGACY_WORK_ITEM}-R0-REVIEW"
    result = rr_identity_result([rr_review_text(extra_fields=(("MESSAGE_ID", value),))])
    assert result["status"] == "RESPONSE_IDENTITY_VERIFIED"
    assert result["review"]["RESPONSE_MESSAGE_ID"] == value


def test_wrong_response_message_id_is_rejected() -> None:
    result = rr_identity_result([rr_review_text(extra_fields=(
        ("MESSAGE_ID", f"{LEGACY_WORK_ITEM}-R0-REVIEW-OTHER"),
    ))])
    assert result["status"] == "RESPONSE_IDENTITY_REJECTED"


def test_exact_rr_review_message_type_is_accepted() -> None:
    result = rr_identity_result([rr_review_text(extra_fields=(("MESSAGE_TYPE", "RR_REVIEW"),))])
    assert result["status"] == "RESPONSE_IDENTITY_VERIFIED"
    assert result["review"]["RESPONSE_MESSAGE_TYPE"] == "RR_REVIEW"


def test_wrong_response_message_type_is_rejected() -> None:
    result = rr_identity_result([rr_review_text(extra_fields=(("MESSAGE_TYPE", "EVIDENCE_PACKET"),))])
    assert result["status"] == "RESPONSE_IDENTITY_REJECTED"


def test_duplicate_response_message_id_is_rejected() -> None:
    value = f"{LEGACY_WORK_ITEM}-R0-REVIEW"
    result = rr_identity_result([rr_review_text(extra_fields=(
        ("MESSAGE_ID", value), ("MESSAGE_ID", value),
    ))])
    assert result["status"] == "RESPONSE_IDENTITY_REJECTED"


def test_duplicate_response_message_type_is_rejected() -> None:
    result = rr_identity_result([rr_review_text(extra_fields=(
        ("MESSAGE_TYPE", "RR_REVIEW"), ("MESSAGE_TYPE", "RR_REVIEW"),
    ))])
    assert result["status"] == "RESPONSE_IDENTITY_REJECTED"


def test_unknown_top_level_field_is_rejected() -> None:
    result = rr_identity_result([rr_review_text(extra_fields=(("UNKNOWN_FIELD", "value"),))])
    assert result["status"] == "RESPONSE_PROTOCOL_REJECTED"


def test_legacy_reply_alias_with_valid_message_metadata_is_accepted() -> None:
    result = rr_identity_result([rr_review_text(
        reply_field="REPLY_TO_MESSAGE_ID",
        extra_fields=(
            ("MESSAGE_ID", f"{LEGACY_WORK_ITEM}-R0-REVIEW"),
            ("MESSAGE_TYPE", "RR_REVIEW"),
        ),
    )])
    assert result["status"] == "RESPONSE_IDENTITY_VERIFIED"
    assert result["review"]["REPLY_ID_SOURCE"] == "LEGACY_ALIAS"


def test_work_item_and_round_remain_exact_with_optional_metadata() -> None:
    result = rr_identity_result([rr_review_text(extra_fields=(
        ("MESSAGE_ID", f"{LEGACY_WORK_ITEM}-R0-REVIEW"),
        ("MESSAGE_TYPE", "RR_REVIEW"),
    ))])
    assert result["review"]["WORK_ITEM_ID"] == LEGACY_WORK_ITEM
    assert result["review"]["ROUND"] == "0"


def test_response_source_is_bound_to_detail_result() -> None:
    sent, state, _, command, env = run_send_case([
        legacy_status(f"https://chatgpt.com/c/{OLD_ID}"), legacy_history(),
        legacy_result([{"Status": "New conversation started"}]),
        legacy_status("https://chatgpt.com/new"), legacy_result([]),
        legacy_result(returncode=1, timed_out=True),
        legacy_status(f"https://chatgpt.com/c/{NEW_ID}"),
        legacy_history(OLD_ID, NEW_ID), legacy_detail(),
    ])
    assert sent.returncode == 2
    completed, state, _ = run_recover(command, env)
    assert completed.returncode == 0
    assert state["response_source_kind"] == "DETAIL_RESULT"
    assert state["response_source_conversation_id"] == NEW_ID
    assert state["verified_target_conversation_id"] == NEW_ID
    assert state["response_raw_output_path"] in state["raw_outputs"]


def synthetic_accept_state(verified_target: str) -> dict:
    return {
        "actual_delivery_conversation_id": None,
        "verified_target_conversation_id": verified_target,
        "work_item_id": LEGACY_WORK_ITEM,
        "message_id": LEGACY_MESSAGE_ID,
        "round": 0,
        "official_response_eligible": False,
        "response_identity_status": "RESPONSE_PENDING",
        "verified_rr_review": None,
        "transitions": [],
    }


def response_batch(conversation_id: str = NEW_ID) -> object:
    return TRANSPORT_MODULE.ResponseMessageBatch(
        conversation_id=conversation_id,
        messages=(
            {"Role": "user", "Text": (
                f"WORK_ITEM_ID: {LEGACY_WORK_ITEM}\n"
                f"MESSAGE_ID: {LEGACY_MESSAGE_ID}\nROUND: 0"
            )},
            {"Role": "assistant", "Text": rr_review_text(), "Generating": False},
        ),
        source_kind="SYNTHETIC_LOCAL_TEST",
        raw_output_path=None,
    )


def test_accept_delivery_cannot_overwrite_verified_target() -> None:
    state = synthetic_accept_state(OLD_ID)
    TRANSPORT_MODULE.accept_delivery(state, response_batch(NEW_ID))
    assert state["verified_target_conversation_id"] == OLD_ID
    assert state["response_identity_status"] == "RESPONSE_SOURCE_CONVERSATION_MISMATCH"
    assert state["official_response_eligible"] is False


def test_wrong_messages_cannot_be_paired_with_expected_conversation() -> None:
    batch = response_batch(OLD_ID)
    try:
        batch.conversation_id = NEW_ID
    except AttributeError:
        pass
    else:
        raise AssertionError("ResponseMessageBatch source must be immutable")
    state = synthetic_accept_state(NEW_ID)
    TRANSPORT_MODULE.accept_delivery(state, batch)
    assert state["response_identity_status"] == "RESPONSE_SOURCE_CONVERSATION_MISMATCH"
    assert state["official_response_eligible"] is False


def duplicate_outbound_messages() -> list[dict]:
    outbound = (
        f"WORK_ITEM_ID: {LEGACY_WORK_ITEM}\n"
        f"MESSAGE_ID: {LEGACY_MESSAGE_ID}\nROUND: 0"
    )
    return [
        {"Role": "user", "Text": outbound},
        {"Role": "user", "Text": outbound},
        {"Role": "assistant", "Text": rr_review_text(), "Generating": False},
    ]


def test_duplicate_outbound_messages_are_ambiguous() -> None:
    result = TRANSPORT_MODULE.verify_rr_response_identity(
        duplicate_outbound_messages(), NEW_ID, NEW_ID,
        LEGACY_WORK_ITEM, LEGACY_MESSAGE_ID, 0,
    )
    assert result["status"] == "OUTBOUND_MESSAGE_IDENTITY_AMBIGUOUS"
    assert result["outbound_message_match_count"] == 2
    assert result["review"] is None


def test_duplicate_outbound_identity_cannot_enter_official_parser() -> None:
    original = TRANSPORT_MODULE.rr_response_fields

    def forbidden_parser(_: str) -> dict:
        raise AssertionError("official parser was entered after an ambiguous outbound anchor")

    TRANSPORT_MODULE.rr_response_fields = forbidden_parser
    try:
        result = TRANSPORT_MODULE.verify_rr_response_identity(
            duplicate_outbound_messages(), NEW_ID, NEW_ID,
            LEGACY_WORK_ITEM, LEGACY_MESSAGE_ID, 0,
        )
    finally:
        TRANSPORT_MODULE.rr_response_fields = original
    assert result["status"] == "OUTBOUND_MESSAGE_IDENTITY_AMBIGUOUS"


def test_exact_rr_review_envelope_is_accepted() -> None:
    result = rr_identity_result([rr_review_text()])
    assert result["status"] == "RESPONSE_IDENTITY_VERIFIED"


def test_assistant_quoted_rr_review_is_rejected() -> None:
    result = rr_identity_result([
        "Below is an example, not a formal review:\n\n" + rr_review_text()
    ])
    assert result["status"] == "RESPONSE_IDENTITY_MISSING"
    assert result["review"] is None


def test_rr_review_with_leading_text_is_rejected() -> None:
    result = rr_identity_result(["leading text\n" + rr_review_text()])
    assert result["status"] == "RESPONSE_IDENTITY_MISSING"


def test_rr_review_with_trailing_text_is_rejected() -> None:
    result = rr_identity_result([rr_review_text() + "\ntrailing text"])
    assert result["status"] == "RESPONSE_IDENTITY_MISSING"


def test_rr_review_missing_begin_marker_is_rejected() -> None:
    text = rr_review_text().removeprefix("RR_REVIEW_BEGIN\n")
    result = rr_identity_result([text])
    assert result["status"] == "RESPONSE_IDENTITY_MISSING"


def test_rr_review_missing_end_marker_is_rejected() -> None:
    text = rr_review_text().removesuffix("\nRR_REVIEW_END")
    result = rr_identity_result([text])
    assert result["status"] == "RESPONSE_IDENTITY_MISSING"


def test_rr_response_wrong_work_item_is_rejected() -> None:
    result = rr_identity_result([rr_review_text(work_item_id=f"{LEGACY_WORK_ITEM}-OTHER")])
    assert result["status"] == "RESPONSE_IDENTITY_MISMATCH"
    assert result["review"] is None


def test_rr_response_wrong_in_reply_to_message_is_rejected() -> None:
    result = rr_identity_result([rr_review_text(message_id=f"{LEGACY_MESSAGE_ID}-OTHER")])
    assert result["status"] == "RESPONSE_IDENTITY_MISMATCH"


def test_rr_response_wrong_round_is_rejected() -> None:
    result = rr_identity_result([rr_review_text(round_value="1")])
    assert result["status"] == "RESPONSE_IDENTITY_MISMATCH"


def test_rr_response_missing_identity_field_is_rejected() -> None:
    for field in ("WORK_ITEM_ID", "IN_REPLY_TO_MESSAGE_ID", "ROUND"):
        result = rr_identity_result([rr_review_text(omit=field)])
        expected = (
            "RESPONSE_IDENTITY_REJECTED"
            if field == "IN_REPLY_TO_MESSAGE_ID"
            else "RESPONSE_IDENTITY_MISSING"
        )
        assert result["status"] == expected, field
        assert result["review"] is None


def test_rr_response_work_item_prefix_collision_is_rejected() -> None:
    result = rr_identity_result([rr_review_text(work_item_id=LEGACY_WORK_ITEM[:-1])])
    assert result["status"] == "RESPONSE_IDENTITY_MISMATCH"


def test_rr_response_message_id_prefix_collision_is_rejected() -> None:
    result = rr_identity_result([rr_review_text(message_id=LEGACY_MESSAGE_ID[:-1])])
    assert result["status"] == "RESPONSE_IDENTITY_MISMATCH"


def test_user_quoted_rr_response_is_not_accepted() -> None:
    messages = [
        {"Role": "user", "Text": f"WORK_ITEM_ID: {LEGACY_WORK_ITEM}\nMESSAGE_ID: {LEGACY_MESSAGE_ID}"},
        {"Role": "user", "Text": rr_review_text()},
    ]
    result = TRANSPORT_MODULE.verify_rr_response_identity(
        messages, NEW_ID, NEW_ID, LEGACY_WORK_ITEM, LEGACY_MESSAGE_ID, 0
    )
    assert result["status"] == "RESPONSE_PENDING"


def test_old_round_response_before_target_message_is_not_accepted() -> None:
    messages = [
        {"Role": "assistant", "Text": rr_review_text(round_value="0")},
        {"Role": "user", "Text": f"WORK_ITEM_ID: {LEGACY_WORK_ITEM}\nMESSAGE_ID: {LEGACY_MESSAGE_ID}\nROUND: 1"},
    ]
    result = TRANSPORT_MODULE.verify_rr_response_identity(
        messages, NEW_ID, NEW_ID, LEGACY_WORK_ITEM, LEGACY_MESSAGE_ID, 1
    )
    assert result["status"] == "RESPONSE_PENDING"


def test_correct_response_from_wrong_conversation_is_rejected() -> None:
    result = rr_identity_result([rr_review_text()], source=OLD_ID)
    assert result["status"] == "RESPONSE_SOURCE_CONVERSATION_MISMATCH"
    assert result["review"] is None


def test_multiple_matching_rr_responses_are_ambiguous() -> None:
    result = rr_identity_result([rr_review_text(), rr_review_text()])
    assert result["status"] == "RESPONSE_IDENTITY_AMBIGUOUS"
    assert result["matching_response_count"] == 2
    assert result["review"] is None


def test_identity_failure_does_not_allow_same_message_id_resend() -> None:
    completed, state, calls, command, env = run_send_case([
        legacy_history(OLD_ID), legacy_status(f"https://chatgpt.com/c/{OLD_ID}"),
        legacy_result([{"Status": "New conversation started"}]),
        legacy_status("https://chatgpt.com/new"), legacy_result([]),
        legacy_result([{
            "conversationId": NEW_ID,
            "conversationUrl": f"https://chatgpt.com/c/{NEW_ID}",
            "response": rr_review_text(message_id=f"{LEGACY_MESSAGE_ID}-OTHER"),
        }]),
        legacy_status(f"https://chatgpt.com/c/{NEW_ID}"),
    ], prepare_new=True)
    assert completed.returncode == 2
    assert state["response_identity_status"] == "RESPONSE_IDENTITY_MISMATCH"
    assert state["official_response_eligible"] is False
    repeated = subprocess.run(
        command, capture_output=True, text=True, encoding="utf-8", env=env, check=False
    )
    assert repeated.returncode == 1
    assert "same-ID resend is forbidden" in repeated.stderr
    assert sum(call[1] == "ask" for call in calls) == 1


def main() -> int:
    tests = [
        test_experiment_protocol_module_is_loadable,
        test_opencli_transport_reexports_protocol_api,
        test_direct_opencli_transport_help_still_works,
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
        test_ask_hard_timeout_returns_before_global_budget,
        test_ask_timeout_preserves_recovery_budget,
        test_timeout_does_not_mark_message_as_not_sent,
        test_timeout_forbids_same_message_id_resend,
        test_recover_never_invokes_ask_or_send,
        test_recover_can_bind_conversation_after_ask_timeout,
        test_recover_pending_response_preserves_conversation_id,
        test_recover_accepts_later_identity_bound_rr_review,
        test_manual_recover_uses_fresh_operation_budget,
        test_manual_recover_preserves_original_send_started_at,
        test_pending_response_can_resume_in_new_invocation,
        test_pending_resume_uses_fresh_operation_budget,
        test_pending_resume_never_invokes_ask_send_or_new,
        test_pending_resume_does_not_change_send_count,
        test_pending_resume_requires_saved_conversation,
        test_pending_resume_preserves_message_identity,
        test_pending_resume_remains_pending_for_incomplete_reply,
        test_pending_resume_accepts_later_complete_rr_review,
        test_pending_resume_rejects_wrong_reply_identity,
        test_pending_resume_stops_at_configured_limit,
        test_compact_packet_payload_is_single_line_and_lossless,
        test_compact_packet_identity_is_accepted_with_formatter_suffix,
        test_compact_packet_wrong_identity_is_rejected,
        test_send_passes_one_complete_single_line_packet_to_opencli,
        test_manual_recover_has_independent_attempt_budget,
        test_manual_recover_never_invokes_ask_send_or_new,
        test_manual_recover_does_not_change_send_count,
        test_empty_status_does_not_erase_candidate_conversation_id,
        test_conflicting_candidate_is_not_silently_overwritten,
        test_candidate_is_not_verified_target,
        test_exact_detail_promotes_candidate_to_verified_target,
        test_old_timeout_state_can_run_one_manual_recover,
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
        test_rr_response_exact_identity_is_accepted,
        test_canonical_in_reply_to_message_id_is_accepted,
        test_exact_legacy_reply_to_message_id_is_normalized,
        test_legacy_alias_wrong_message_id_is_rejected,
        test_canonical_and_alias_same_value_are_accepted,
        test_canonical_and_alias_conflict_is_rejected,
        test_duplicate_legacy_alias_is_rejected,
        test_missing_reply_identity_fields_is_rejected,
        test_legacy_alias_does_not_bypass_rr_envelope_validation,
        test_optional_response_message_metadata_does_not_contaminate_fields,
        test_exact_response_message_id_is_accepted,
        test_wrong_response_message_id_is_rejected,
        test_exact_rr_review_message_type_is_accepted,
        test_wrong_response_message_type_is_rejected,
        test_duplicate_response_message_id_is_rejected,
        test_duplicate_response_message_type_is_rejected,
        test_unknown_top_level_field_is_rejected,
        test_legacy_reply_alias_with_valid_message_metadata_is_accepted,
        test_work_item_and_round_remain_exact_with_optional_metadata,
        test_response_source_is_bound_to_detail_result,
        test_accept_delivery_cannot_overwrite_verified_target,
        test_wrong_messages_cannot_be_paired_with_expected_conversation,
        test_duplicate_outbound_messages_are_ambiguous,
        test_duplicate_outbound_identity_cannot_enter_official_parser,
        test_exact_rr_review_envelope_is_accepted,
        test_assistant_quoted_rr_review_is_rejected,
        test_rr_review_with_leading_text_is_rejected,
        test_rr_review_with_trailing_text_is_rejected,
        test_rr_review_missing_begin_marker_is_rejected,
        test_rr_review_missing_end_marker_is_rejected,
        test_rr_response_wrong_work_item_is_rejected,
        test_rr_response_wrong_in_reply_to_message_is_rejected,
        test_rr_response_wrong_round_is_rejected,
        test_rr_response_missing_identity_field_is_rejected,
        test_rr_response_work_item_prefix_collision_is_rejected,
        test_rr_response_message_id_prefix_collision_is_rejected,
        test_user_quoted_rr_response_is_not_accepted,
        test_old_round_response_before_target_message_is_not_accepted,
        test_correct_response_from_wrong_conversation_is_rejected,
        test_multiple_matching_rr_responses_are_ambiguous,
        test_identity_failure_does_not_allow_same_message_id_resend,
    ]
    for test in tests:
        test()
        print(f"PASS: {test.__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
