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
from typing import Any
from urllib.parse import urlparse


PROCESS_MONOTONIC_STARTED = time.monotonic()
PROCESS_STARTED_AT = datetime.now(timezone.utc).isoformat(timespec="seconds")
COMMAND_WAIT_SECONDS = 15
POLL_INTERVAL_SECONDS = 5
TOTAL_RESPONSE_WAIT_SECONDS = 30
MAX_SEND_ATTEMPTS_PER_MESSAGE = 1
MAX_RECOVERY_ATTEMPTS = 1
MAX_DETAIL_CHECKS = 1
MAX_EXTERNAL_COMMANDS = 8
MAX_EXPERIMENT_SECONDS = 60
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
    "FAILED",
}
NO_RESEND_STATES = DELIVERY_STATES - {"NOT_SENT"}


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


def command(state: dict[str, Any], state_path: Path, label: str, args: list[str], timeout: int) -> dict[str, Any] | None:
    if state["external_command_count"] >= state["parameters"]["max_external_commands"]:
        stop(state, "EXPERIMENT_BUDGET_EXHAUSTED: MAX_EXTERNAL_COMMANDS")
        return None
    started = datetime.fromisoformat(state["started_at"])
    elapsed = (datetime.now(timezone.utc) - started).total_seconds()
    if elapsed >= state["parameters"]["max_experiment_seconds"]:
        stop(state, "EXPERIMENT_BUDGET_EXHAUSTED: MAX_EXPERIMENT_SECONDS")
        return None
    state["external_command_count"] += 1
    result = run_opencli(args, min(timeout, max(1, int(state["parameters"]["max_experiment_seconds"] - elapsed))))
    save_raw(state, state_path, label, result)
    return result


def result_rows(result: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not result or result["timed_out"] or result["returncode"] != 0:
        return []
    return rows(parse_json(result["stdout"]))


def status_url(result: dict[str, Any] | None) -> str | None:
    for row in result_rows(result):
        url = pick(row, "Url")
        if url:
            return str(url)
    return None


def marker(message_id: str) -> str:
    return f"MESSAGE_ID: {message_id}"


def inspect_messages(messages: list[dict[str, Any]], work_item_id: str, message_id: str) -> tuple[bool, bool, bool]:
    user_index: int | None = None
    for index, message in enumerate(messages):
        role = str(pick(message, "Role") or "").lower()
        text = str(pick(message, "Text") or "")
        if role == "user" and marker(message_id) in text and f"WORK_ITEM_ID: {work_item_id}" in text:
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
        "schema_version": 3,
        "work_item_id": args.work_item_id,
        "operation": "PREPARE_NEW",
        "pre_operation_url": None,
        "pre_operation_conversation_id": None,
        "post_operation_url": None,
        "verification_result": "NOT_RUN",
        "read_result": "NOT_RUN",
        "message_send_count": 0,
        "external_command_count": 0,
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
    state["external_command_count"] += 1
    persist_prepare(state, state_path)
    result = run_opencli(args, max(0.001, min(state["parameters"]["command_wait_seconds"], remaining)))
    save_raw(state, state_path, label, result)
    persist_prepare(state, state_path)
    if result["timed_out"] or time.monotonic() - state["_monotonic_started"] >= state["parameters"]["max_experiment_seconds"]:
        finish_prepare(state, "BUDGET_EXHAUSTED", "BUDGET_EXHAUSTED")
        persist_prepare(state, state_path)
        return None
    return result


def prepare_new_command(args: argparse.Namespace) -> int:
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
        state["pre_operation_url"] = status_url(pre_status)
        state["pre_operation_conversation_id"] = conversation_id_from_url(state["pre_operation_url"] or "")
        persist_prepare(state, state_path)
    if pre_status is not None and (
        pre_status["timed_out"] or pre_status["returncode"] != 0 or not state["pre_operation_url"]
    ):
        finish_prepare(state, "BLOCKED_BEFORE_SEND", "PRE_OPERATION_STATUS_UNVERIFIED")
        persist_prepare(state, state_path)
        pre_status = None
    created = None if pre_status is None else prepare_external_command(
        state, state_path, "new",
        ["chatgpt", "new", "-f", "json", "--window", "background"],
    )
    created_ok = bool(result_rows(created))
    post_status = None if not created_ok else prepare_external_command(
        state, state_path, "status-after-prepare",
        ["chatgpt", "status", "-f", "json", "--window", "background"],
    )
    if post_status is not None:
        state["post_operation_url"] = status_url(post_status)
        if blank_new_url(state["post_operation_url"], state["pre_operation_conversation_id"]):
            state["verification_result"] = "NEW_BLANK_URL_VERIFIED"
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
        parsed = parse_json(read["stdout"])
        empty = read["returncode"] == 0 and not read["timed_out"] and (
            str(read["stdout"]).strip() == "EMPTY_RESULT" or parsed == []
        )
        state["read_result"] = "EMPTY_RESULT" if empty else "NON_EMPTY_OR_UNRELIABLE"
        if empty:
            finish_prepare(state, "PREPARED_NEW_CONVERSATION", "STOP_WITHOUT_SEND")
        else:
            finish_prepare(state, "BLOCKED_BEFORE_SEND", "READ_NOT_EMPTY")
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
        "schema_version": 2, "work_item_id": args.work_item_id, "message_id": args.message_id,
        "round": args.round, "message_type": args.message_type,
        "expected_conversation_mode": "EXISTING" if args.conversation else "NEW",
        "pre_send_active_conversation_id": None, "verified_target_conversation_id": args.conversation,
        "actual_delivery_conversation_id": None, "verified_target_url": None,
        "delivery_state": "NOT_SENT", "work_item_state": "IN_PROGRESS",
        "send_attempt_count": 0, "recovery_attempt_count": 0, "detail_check_count": 0,
        "external_command_count": 0, "misroute_detected": False,
        "official_response_eligible": False, "started_at": utc_now(), "stopped_at": None,
        "stop_reason": None, "updated_at": utc_now(), "state_file": str(state_path),
        "raw_outputs": [], "transitions": [],
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


def history(state: dict[str, Any], state_path: Path) -> list[dict[str, Any]]:
    result = command(state, state_path, "history", ["chatgpt", "history", "--limit", str(state["parameters"]["recent_candidate_limit"]), "-f", "json", "--window", "background"], state["parameters"]["command_wait_seconds"])
    return result_rows(result)


def detail(state: dict[str, Any], state_path: Path, identity: str) -> tuple[list[dict[str, Any]], str | None]:
    if state["detail_check_count"] >= state["parameters"]["max_detail_checks"]:
        return [], None
    state["detail_check_count"] += 1
    result = command(state, state_path, "detail", ["chatgpt", "detail", identity, "-f", "json", "--window", "background"], state["parameters"]["command_wait_seconds"])
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


def recover_delivery(state: dict[str, Any], state_path: Path, returned_identity: str | None = None) -> bool:
    if state["recovery_attempt_count"] >= state["parameters"]["max_recovery_attempts"]:
        stop(state, "EXPERIMENT_BUDGET_EXHAUSTED: MAX_RECOVERY_ATTEMPTS")
        return False
    state["recovery_attempt_count"] += 1
    candidates: list[str] = []
    status = command(state, state_path, "status-after-send", ["chatgpt", "status", "-f", "json", "--window", "background"], state["parameters"]["command_wait_seconds"])
    current_url = status_url(status)
    current_id = conversation_id_from_url(current_url or "")
    if current_id:
        candidates.append(current_id)
    if returned_identity and returned_identity not in candidates:
        candidates.append(returned_identity)
    if not candidates and state["external_command_count"] < state["parameters"]["max_external_commands"]:
        for row in history(state, state_path):
            identity, _ = conversation_identity(row)
            if identity and identity not in candidates:
                candidates.append(identity)
    for identity in candidates[:state["parameters"]["recent_candidate_limit"]]:
        messages, raw_path = detail(state, state_path, identity)
        delivered, response_exists, ready = inspect_messages(messages, state["work_item_id"], state["message_id"])
        if not delivered:
            continue
        if identity in pre_send_ids(state):
            mark_misroute(state, identity, raw_path)
        else:
            accept_delivery(state, identity, ready, response_exists)
        return True
    if not state.get("stopped_at"):
        set_state(state, "DELIVERY_UNKNOWN", "bounded exact-ID recovery found no delivery")
        stop(state, "DELIVERY_UNKNOWN: do not resend this Message ID")
    return False


def verify_new_conversation(state: dict[str, Any], state_path: Path, manual_url: str | None) -> bool:
    set_state(state, "CREATING_CONVERSATION", "create a blank conversation without sending")
    if not manual_url:
        created = command(state, state_path, "new", ["chatgpt", "new", "-f", "json", "--window", "background"], state["parameters"]["command_wait_seconds"])
        if not result_rows(created):
            stop(state, "CREATE_NEW_CONVERSATION_UNVERIFIED: use a manually opened blank ChatGPT URL")
            return False
    set_state(state, "VERIFYING_CONVERSATION", "verify URL changed and blank page has no messages")
    status = command(state, state_path, "status-new", ["chatgpt", "status", "-f", "json", "--window", "background"], state["parameters"]["command_wait_seconds"])
    if status is None:
        return False
    url = status_url(status)
    if manual_url and url != manual_url:
        stop(state, "VERIFY_NEW_CONVERSATION_FAILED: current URL does not match manual blank URL")
        return False
    if not blank_new_url(url, state["pre_send_active_conversation_id"]):
        stop(state, "VERIFY_NEW_CONVERSATION_FAILED: still on an old /c/<id> page or URL is not a blank ChatGPT page")
        return False
    read_result = command(state, state_path, "read-new", ["chatgpt", "read", "-f", "json", "--window", "background"], state["parameters"]["command_wait_seconds"])
    if read_result is None:
        return False
    if read_result is None or read_result["timed_out"] or read_result["returncode"] != 0 or result_rows(read_result):
        stop(state, "VERIFY_NEW_CONVERSATION_FAILED: blank-page read was not empty and reliable")
        return False
    state["verified_target_url"] = url
    return True


def send_command(args: argparse.Namespace) -> int:
    state_path = Path(args.state_file) if args.state_file else default_state_path(args.work_item_id, args.message_id)
    if state_path.exists():
        existing = read_json(state_path)
        if existing.get("message_id") != args.message_id:
            raise ValueError("existing state file belongs to another MESSAGE_ID")
        if existing.get("delivery_state") in NO_RESEND_STATES or existing.get("send_attempt_count", 0) >= 1:
            raise ValueError(f"MESSAGE_ID already has state {existing.get('delivery_state')}; same-ID resend is forbidden")
    state = new_state(args, state_path)
    payload = prepare_payload(args, read_payload(args))
    pre_status = command(state, state_path, "status-before-send", ["chatgpt", "status", "-f", "json", "--window", "background"], args.command_wait_seconds)
    pre_url = status_url(pre_status)
    state["pre_send_active_conversation_id"] = conversation_id_from_url(pre_url or "")
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
        if not verify_new_conversation(state, state_path, args.manual_new_url):
            write_json(state_path, state)
            return output_state(state)
        target = []
    if state["send_attempt_count"] >= state["parameters"]["max_send_attempts_per_message"]:
        stop(state, "EXPERIMENT_BUDGET_EXHAUSTED: MAX_SEND_ATTEMPTS_PER_MESSAGE")
        write_json(state_path, state)
        return output_state(state)
    state["send_attempt_count"] += 1
    set_state(state, "SENDING", "single ask on verified target")
    # Persist the one permitted send attempt before invoking the write command.
    # A process crash during ask must still make a same-ID retry impossible.
    write_json(state_path, state)
    result = command(state, state_path, "ask", ["chatgpt", "ask", payload, *target, "--timeout", str(args.command_wait_seconds), "-f", "json", "--window", "background"], args.command_wait_seconds + 5)
    if result is None:
        write_json(state_path, state)
        return output_state(state)
    returned_id, returned_url = (None, None)
    for row in result_rows(result):
        returned_id, returned_url = conversation_identity(row)
        if returned_id or returned_url:
            break
    returned_id = returned_id or conversation_id_from_url(returned_url or "")
    if result["timed_out"] or result["returncode"] != 0:
        set_state(state, "DELIVERY_UNKNOWN", "ask timed out or returned nonzero; one bounded recovery only")
        recover_delivery(state, state_path, returned_id)
    elif returned_id and returned_id in pre_send_ids(state) and not args.conversation:
        mark_misroute(state, returned_id, state["raw_outputs"][-1])
    elif returned_id:
        state["actual_delivery_conversation_id"] = returned_id
        state["verified_target_conversation_id"] = returned_id
        state["official_response_eligible"] = True
        response = next((pick(row, "response") for row in result_rows(result) if pick(row, "response")), None)
        set_state(state, "RESPONSE_READY" if response else "DELIVERED", "ask returned verified new conversation identity")
        stop(state, "RESPONSE_READY" if response else "BOUNDED_WAIT_COMPLETE", "ACHIEVED" if response else "IN_PROGRESS")
    else:
        set_state(state, "DELIVERY_UNKNOWN", "ask returned without conversation identity")
        recover_delivery(state, state_path)
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
