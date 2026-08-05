"""Pure-local public-CLI tests for the RR Lead OpenCLI transport."""

from __future__ import annotations

import json
import importlib.util
import io
import os
import subprocess
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
TRANSPORT = ROOT / "skills" / "research-review-lead" / "scripts" / "opencli_transport.py"
sys.dont_write_bytecode = True
OLD_ID = "old-conversation"
WORK_ITEM = "SYNTHETIC-A2P1-001"
LEGACY_WORK_ITEM = "SYNTHETIC-TRANSPORT-001"
LEGACY_MESSAGE_ID = f"{LEGACY_WORK_ITEM}-R0-SMOKE"
NEW_ID = "new-conversation"

SPEC = importlib.util.spec_from_file_location("opencli_transport", TRANSPORT)
assert SPEC and SPEC.loader
transport = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(transport)


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
time.sleep(item.get("sleep", 0))
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


def success_sequence(read: object = "EMPTY_RESULT", post_url: str = "https://chatgpt.com/new") -> list[dict[str, object]]:
    return [
        status(f"https://chatgpt.com/c/{OLD_ID}"),
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


def test_old_conversation_to_new_and_empty_result() -> None:
    completed, state, calls, runtime = run_prepare(success_sequence())
    assert completed.returncode == 0
    assert state["test_result"] == "PREPARED_NEW_CONVERSATION"
    assert state["pre_operation_conversation_id"] == OLD_ID
    assert state["post_operation_url"] == "https://chatgpt.com/new"
    assert state["read_result"] == "EMPTY_RESULT"
    assert state["message_send_count"] == 0
    assert (runtime / "prepare-new-state.json").is_file()
    assert_no_send(calls)


def test_empty_json_also_verifies_blank_page() -> None:
    completed, state, calls, _ = run_prepare(success_sequence([]))
    assert completed.returncode == 0
    assert state["test_result"] == "PREPARED_NEW_CONVERSATION"
    assert state["read_result"] == "EMPTY_RESULT"
    assert_no_send(calls)


def test_runtime_contains_required_a2p1_fields() -> None:
    _, state, _, _ = run_prepare(success_sequence())
    required = {
        "work_item_id", "operation", "pre_operation_url",
        "pre_operation_conversation_id", "post_operation_url",
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
    assert state["read_result"] == "NON_EMPTY_OR_UNRELIABLE"
    assert state["test_result"] == "BLOCKED_BEFORE_SEND"
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


def legacy_args(root: Path, *, max_external_commands: int = 8) -> SimpleNamespace:
    message_file = root / "message.txt"
    message_file.write_text("synthetic body", encoding="utf-8")
    return SimpleNamespace(
        work_item_id=LEGACY_WORK_ITEM, message_id=LEGACY_MESSAGE_ID, round=0,
        message_type="TRANSPORT_SMOKE", conversation=None, manual_new_url=None,
        message_file=str(message_file), state_file=str(root / "state.json"),
        command_wait_seconds=15, max_recovery_attempts=1, max_detail_checks=1,
        max_external_commands=max_external_commands, max_experiment_seconds=60,
        recent_candidate_limit=3,
    )


def run_send_case(sequence: list[dict], *, max_external_commands: int = 8) -> tuple[int, dict]:
    root = Path(tempfile.mkdtemp(prefix="rr-send-regression-"))
    case_args = legacy_args(root, max_external_commands=max_external_commands)
    with patch.object(transport, "run_opencli", side_effect=sequence) as mocked:
        with redirect_stdout(io.StringIO()):
            exit_code = transport.send_command(case_args)
        assert mocked.call_count <= max_external_commands
    return exit_code, json.loads(Path(case_args.state_file).read_text(encoding="utf-8"))


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
    exit_code, state = run_send_case([
        legacy_status(f"https://chatgpt.com/c/{OLD_ID}"), legacy_history(),
        legacy_result([{"Status": "New conversation started"}]),
        legacy_status("https://chatgpt.com/new"), legacy_result([]),
        legacy_result([{"conversationId": NEW_ID, "conversationUrl": f"https://chatgpt.com/c/{NEW_ID}", "response": "ok"}]),
    ])
    assert exit_code == 0
    assert state["delivery_state"] == "RESPONSE_READY"
    assert state["send_attempt_count"] == 1


def test_send_timeout_recovery_regression() -> None:
    exit_code, state = run_send_case([
        legacy_status(f"https://chatgpt.com/c/{OLD_ID}"), legacy_history(),
        legacy_result([{"Status": "New conversation started"}]),
        legacy_status("https://chatgpt.com/new"), legacy_result([]),
        legacy_result(returncode=1, timed_out=True),
        legacy_status(f"https://chatgpt.com/c/{NEW_ID}"), legacy_detail(),
    ])
    assert exit_code == 0
    assert state["delivery_state"] == "RESPONSE_READY"
    assert state["recovery_attempt_count"] == 1


def test_send_misroute_regression() -> None:
    exit_code, state = run_send_case([
        legacy_status(f"https://chatgpt.com/c/{OLD_ID}"), legacy_history(),
        legacy_result([{"Status": "New conversation started"}]),
        legacy_status("https://chatgpt.com/new"), legacy_result([]),
        legacy_result(returncode=1, stderr="navigated away"),
        legacy_status(f"https://chatgpt.com/c/{OLD_ID}"), legacy_detail(),
    ])
    assert exit_code == 2
    assert state["delivery_state"] == "MISROUTED_DELIVERY"
    assert state["official_response_eligible"] is False


def test_send_same_message_id_rejected_regression() -> None:
    root = Path(tempfile.mkdtemp(prefix="rr-resend-regression-"))
    case_args = legacy_args(root)
    stored = transport.new_state(case_args, Path(case_args.state_file))
    stored["delivery_state"] = "MISROUTED_DELIVERY"
    stored["send_attempt_count"] = 1
    transport.write_json(Path(case_args.state_file), stored)
    try:
        transport.send_command(case_args)
    except ValueError as error:
        assert "same-ID resend is forbidden" in str(error)
    else:
        raise AssertionError("same Message ID was not rejected")


def test_send_external_budget_regression() -> None:
    exit_code, state = run_send_case([
        legacy_status(f"https://chatgpt.com/c/{OLD_ID}"), legacy_history(),
        legacy_result([{"Status": "New conversation started"}]),
    ], max_external_commands=3)
    assert exit_code == 2
    assert state["send_attempt_count"] == 0
    assert state["external_command_count"] == 3


def main() -> int:
    tests = [
        test_help_exposes_prepare_new,
        test_old_conversation_to_new_and_empty_result,
        test_empty_json_also_verifies_blank_page,
        test_runtime_contains_required_a2p1_fields,
        test_old_conversation_still_active_fails,
        test_existing_messages_fail,
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
