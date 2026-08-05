"""Pure-local public-CLI tests for the RR Lead OpenCLI transport."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TRANSPORT = ROOT / "skills" / "research-review-lead" / "scripts" / "opencli_transport.py"
REAL_EMPTY_RESULT_FIXTURE = ROOT / "scripts" / "fixtures" / "transport-a2p1-read-empty-result.json"
sys.dont_write_bytecode = True
OLD_ID = "old-conversation"
WORK_ITEM = "SYNTHETIC-A2P1-001"
LEGACY_WORK_ITEM = "SYNTHETIC-TRANSPORT-001"
LEGACY_MESSAGE_ID = f"{LEGACY_WORK_ITEM}-R0-SMOKE"
NEW_ID = "new-conversation"

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
    }
    assert required <= state.keys()
    assert state["operation"] == "PREPARE_NEW"
    assert state["message_send_count"] == 0
    assert state["external_command_count"] == 4
    assert state["parameters"]["max_recovery_attempts"] == 0
    assert state["parameters"]["max_detail_checks"] == 0


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


def send_cli_command(root: Path, *, max_external_commands: int = 8) -> list[str]:
    message_file = root / "message.txt"
    message_file.write_text("synthetic body", encoding="utf-8")
    return [
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


def run_send_case(
    sequence: list[dict], *, max_external_commands: int = 8
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
    command = send_cli_command(root, max_external_commands=max_external_commands)
    completed = subprocess.run(
        command, capture_output=True, text=True, encoding="utf-8", env=env, check=False
    )
    state = json.loads((root / "state.json").read_text(encoding="utf-8"))
    calls = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert len(calls) <= max_external_commands
    return completed, state, calls, command, env


def legacy_status(url: str) -> dict:
    return legacy_result([{"Status": "Connected", "Login": "Yes", "Url": url}])


def legacy_history() -> dict:
    return legacy_result([{"Id": OLD_ID, "Title": "pre-existing", "Url": f"https://chatgpt.com/c/{OLD_ID}"}])


def legacy_detail(ready: bool = True) -> dict:
    messages = [{"Role": "user", "Text": f"WORK_ITEM_ID: {LEGACY_WORK_ITEM}\nMESSAGE_ID: {LEGACY_MESSAGE_ID}"}]
    if ready:
        messages.append({"Role": "assistant", "Text": "synthetic response", "Generating": False, "StableSeconds": 3})
    return legacy_result(messages)


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


def test_send_timeout_recovery_regression() -> None:
    completed, state, _, _, _ = run_send_case([
        legacy_status(f"https://chatgpt.com/c/{OLD_ID}"), legacy_history(),
        legacy_result([{"Status": "New conversation started"}]),
        legacy_status("https://chatgpt.com/new"), legacy_result([]),
        legacy_result(returncode=1, timed_out=True),
        legacy_status(f"https://chatgpt.com/c/{NEW_ID}"), legacy_detail(),
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
        legacy_status(f"https://chatgpt.com/c/{OLD_ID}"), legacy_detail(),
    ])
    assert completed.returncode == 2
    assert state["delivery_state"] == "MISROUTED_DELIVERY"
    assert state["official_response_eligible"] is False


def test_send_same_message_id_rejected_regression() -> None:
    completed, _, calls, command, env = run_send_case([
        legacy_status(f"https://chatgpt.com/c/{OLD_ID}"), legacy_history(),
        legacy_result([{"Status": "New conversation started"}]),
        legacy_status("https://chatgpt.com/new"), legacy_result([]),
        legacy_result([{"conversationId": NEW_ID, "conversationUrl": f"https://chatgpt.com/c/{NEW_ID}", "response": "ok"}]),
    ])
    assert completed.returncode == 0
    repeated = subprocess.run(
        command, capture_output=True, text=True, encoding="utf-8", env=env, check=False
    )
    assert repeated.returncode == 1
    assert "same-ID resend is forbidden" in repeated.stderr
    assert len(calls) == 6


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
        test_send_timeout_recovery_regression,
        test_send_misroute_regression,
        test_send_same_message_id_rejected_regression,
        test_send_external_budget_regression,
    ]
    for test in tests:
        test()
        print(f"PASS: {test.__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
