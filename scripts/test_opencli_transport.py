"""Pure-local synthetic tests for the RR Lead OpenCLI transport."""

from __future__ import annotations

import importlib.util
import io
import json
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
TRANSPORT = ROOT / "skills" / "research-review-lead" / "scripts" / "opencli_transport.py"
SPEC = importlib.util.spec_from_file_location("opencli_transport", TRANSPORT)
assert SPEC and SPEC.loader
transport = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(transport)

OLD_ID = "old-conversation"
NEW_ID = "new-conversation"
WORK_ITEM = "SYNTHETIC-TRANSPORT-001"
MESSAGE_ID = f"{WORK_ITEM}-R0-SMOKE"


def result(stdout: object = None, *, returncode: int = 0, timed_out: bool = False, stderr: str = "") -> dict:
    return {
        "started_at": "2026-08-05T00:00:00+00:00",
        "finished_at": "2026-08-05T00:00:01+00:00",
        "timed_out": timed_out,
        "returncode": returncode,
        "stdout": stdout if isinstance(stdout, str) else json.dumps(stdout if stdout is not None else []),
        "stderr": stderr,
    }


def status(url: str) -> dict:
    return result([{"Status": "Connected", "Login": "Yes", "Url": url}])


def history() -> dict:
    return result([{"Id": OLD_ID, "Title": "pre-existing", "Url": f"https://chatgpt.com/c/{OLD_ID}"}])


def new_blank() -> dict:
    return result([{"Status": "New conversation started"}])


def detail(identity: str, ready: bool = True) -> dict:
    messages = [
        {"Role": "user", "Text": f"WORK_ITEM_ID: {WORK_ITEM}\nMESSAGE_ID: {MESSAGE_ID}"},
    ]
    if ready:
        messages.append({"Role": "assistant", "Text": "synthetic response", "Generating": False, "StableSeconds": 3})
    return result(messages)


def args(root: Path, *, max_external_commands: int = 8) -> SimpleNamespace:
    message_file = root / "message.txt"
    message_file.write_text("synthetic body", encoding="utf-8")
    return SimpleNamespace(
        work_item_id=WORK_ITEM, message_id=MESSAGE_ID, round=0,
        message_type="TRANSPORT_SMOKE", conversation=None, manual_new_url=None,
        message_file=str(message_file), state_file=str(root / "state.json"),
        command_wait_seconds=15, max_recovery_attempts=1, max_detail_checks=1,
        max_external_commands=max_external_commands, max_experiment_seconds=60,
        recent_candidate_limit=3,
    )


def run_case(sequence: list[dict], *, max_external_commands: int = 8) -> tuple[int, dict, SimpleNamespace]:
    root = Path(tempfile.mkdtemp(prefix="rr-transport-test-"))
    case_args = args(root, max_external_commands=max_external_commands)
    with patch.object(transport, "run_opencli", side_effect=sequence) as mocked:
        with redirect_stdout(io.StringIO()):
            exit_code = transport.send_command(case_args)
        assert mocked.call_count <= max_external_commands
    return exit_code, json.loads(Path(case_args.state_file).read_text(encoding="utf-8")), case_args


def test_correct_new_conversation() -> None:
    exit_code, state, _ = run_case([
        status(f"https://chatgpt.com/c/{OLD_ID}"), history(), new_blank(),
        status("https://chatgpt.com/"), result([]),
        result([{"conversationId": NEW_ID, "conversationUrl": f"https://chatgpt.com/c/{NEW_ID}", "response": "ok"}]),
    ])
    assert exit_code == 0
    assert state["delivery_state"] == "RESPONSE_READY"
    assert state["verified_target_conversation_id"] == NEW_ID
    assert state["send_attempt_count"] == 1


def test_timeout_recovers_correct_new_conversation() -> None:
    exit_code, state, _ = run_case([
        status(f"https://chatgpt.com/c/{OLD_ID}"), history(), new_blank(),
        status("https://chatgpt.com/"), result([]),
        result(returncode=1, timed_out=True),
        status(f"https://chatgpt.com/c/{NEW_ID}"), detail(NEW_ID),
    ])
    assert exit_code == 0
    assert state["delivery_state"] == "RESPONSE_READY"
    assert state["actual_delivery_conversation_id"] == NEW_ID
    assert state["recovery_attempt_count"] == 1


def test_message_misrouted_to_old_conversation() -> dict:
    exit_code, state, _ = run_case([
        status(f"https://chatgpt.com/c/{OLD_ID}"), history(), new_blank(),
        status("https://chatgpt.com/"), result([]),
        result(returncode=1, stderr="navigated away"),
        status(f"https://chatgpt.com/c/{OLD_ID}"), detail(OLD_ID),
    ])
    assert exit_code == 2
    assert state["delivery_state"] == "MISROUTED_DELIVERY"
    assert state["work_item_state"] == "BLOCKED"
    assert state["misroute_detected"] is True
    return state


def test_old_conversation_hit_never_promoted() -> None:
    state = test_message_misrouted_to_old_conversation()
    assert state["official_response_eligible"] is False
    assert state["delivery_state"] not in {"DELIVERED", "RESPONSE_PENDING", "RESPONSE_READY"}


def test_same_message_id_second_send_rejected() -> None:
    root = Path(tempfile.mkdtemp(prefix="rr-transport-resend-"))
    case_args = args(root)
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


def test_experiment_budget_stops() -> None:
    exit_code, state, _ = run_case([
        status(f"https://chatgpt.com/c/{OLD_ID}"), history(), new_blank(),
    ], max_external_commands=3)
    assert exit_code == 2
    assert state["send_attempt_count"] == 0
    assert state["external_command_count"] == 3
    assert "MAX_EXTERNAL_COMMANDS" in state["stop_reason"]


def main() -> int:
    tests = [
        test_correct_new_conversation,
        test_timeout_recovers_correct_new_conversation,
        test_message_misrouted_to_old_conversation,
        test_old_conversation_hit_never_promoted,
        test_same_message_id_second_send_rejected,
        test_experiment_budget_stops,
    ]
    for test in tests:
        test()
        print(f"PASS: {test.__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
