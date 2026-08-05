#!/usr/bin/env python3
"""Bounded, idempotent OpenCLI transport for the RR Lead loop.

The script stores identifiers and command evidence, never browser credentials.
It sends a MESSAGE_ID at most once, then recovers and polls without resending.
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


COMMAND_WAIT_SECONDS = 25
POLL_INTERVAL_SECONDS = 5
TOTAL_RESPONSE_WAIT_SECONDS = 120
MAX_RECOVERY_ATTEMPTS = 3
STABLE_SECONDS = 3
HISTORY_LIMIT = 100

DELIVERY_STATES = {
    "NOT_SENT",
    "SENDING",
    "SENT",
    "DELIVERY_UNKNOWN",
    "DELIVERED",
    "RESPONSE_PENDING",
    "RESPONSE_READY",
    "FAILED",
}
NO_RESEND_STATES = DELIVERY_STATES - {"NOT_SENT", "FAILED"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-._")
    if not cleaned:
        raise ValueError("identifier contains no safe filename characters")
    return cleaned[:120]


def default_state_path(work_item_id: str, message_id: str) -> Path:
    root = Path(tempfile.gettempdir()) / "research-review-lead"
    return root / safe_name(work_item_id) / f"{safe_name(message_id)}.json"


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


def save_raw(state: dict[str, Any], state_path: Path, label: str, result: dict[str, Any]) -> None:
    raw_dir = state_path.parent / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    sequence = len(state.setdefault("raw_outputs", [])) + 1
    path = raw_dir / f"{sequence:02d}-{safe_name(label)}.json"
    write_json(path, result)
    state["raw_outputs"].append(str(path))


def find_opencli() -> list[str]:
    candidates = ["opencli.cmd", "opencli.exe", "opencli"]
    for candidate in candidates:
        found = shutil.which(candidate)
        if found:
            if found.lower().endswith(".ps1"):
                return ["powershell", "-NoProfile", "-File", found]
            return [found]
    raise RuntimeError("opencli was not found on PATH")


def run_opencli(args: list[str], timeout: int) -> dict[str, Any]:
    command = [*find_opencli(), *args]
    started = utc_now()
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        return {
            "started_at": started,
            "finished_at": utc_now(),
            "timed_out": False,
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
    except subprocess.TimeoutExpired as error:
        return {
            "started_at": started,
            "finished_at": utc_now(),
            "timed_out": True,
            "returncode": None,
            "stdout": _decode_timeout_stream(error.stdout),
            "stderr": _decode_timeout_stream(error.stderr),
        }


def _decode_timeout_stream(value: bytes | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def parse_json(text: str) -> Any:
    stripped = text.strip()
    if not stripped:
        return None
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        starts = [position for token in ("[", "{") if (position := stripped.find(token)) >= 0]
        if not starts:
            return None
        try:
            return json.loads(stripped[min(starts) :])
        except json.JSONDecodeError:
            return None


def rows(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [row for row in value if isinstance(row, dict)]
    if isinstance(value, dict):
        return [value]
    return []


def pick(row: dict[str, Any], *names: str) -> Any:
    lowered = {str(key).lower(): value for key, value in row.items()}
    for name in names:
        if name.lower() in lowered:
            return lowered[name.lower()]
    return None


def conversation_identity(row: dict[str, Any]) -> tuple[str | None, str | None]:
    conversation_id = pick(row, "Id", "conversationId", "ConversationId")
    url = pick(row, "Url", "conversationUrl", "ConversationUrl")
    return (
        str(conversation_id) if conversation_id else None,
        str(url) if url else None,
    )


def history(state: dict[str, Any], state_path: Path, timeout: int) -> list[dict[str, Any]]:
    result = run_opencli(
        ["chatgpt", "history", "--limit", str(HISTORY_LIMIT), "-f", "json", "--window", "background"],
        timeout,
    )
    save_raw(state, state_path, "history", result)
    if result["timed_out"] or result["returncode"] != 0:
        return []
    return rows(parse_json(result["stdout"]))


def detail(
    state: dict[str, Any], state_path: Path, identity: str, timeout: int
) -> list[dict[str, Any]]:
    result = run_opencli(
        ["chatgpt", "detail", identity, "-f", "json", "--window", "background"],
        timeout,
    )
    save_raw(state, state_path, "detail", result)
    if result["timed_out"] or result["returncode"] != 0:
        return []
    return rows(parse_json(result["stdout"]))


def marker(message_id: str) -> str:
    return f"MESSAGE_ID: {message_id}"


def inspect_messages(messages: list[dict[str, Any]], message_id: str) -> tuple[bool, bool, bool]:
    user_index: int | None = None
    for index, message in enumerate(messages):
        role = str(pick(message, "Role") or "").lower()
        text = str(pick(message, "Text") or "")
        if role == "user" and marker(message_id) in text:
            user_index = index
    if user_index is None:
        return False, False, False

    assistant_messages = []
    for message in messages[user_index + 1 :]:
        if str(pick(message, "Role") or "").lower() == "assistant":
            assistant_messages.append(message)
    if not assistant_messages:
        return True, False, False

    latest = assistant_messages[-1]
    text = str(pick(latest, "Text") or "").strip()
    generating_value = pick(latest, "Generating")
    generating = str(generating_value).lower() == "true" if generating_value is not None else False
    stable_value = pick(latest, "StableSeconds")
    try:
        stable = float(stable_value) >= STABLE_SECONDS if stable_value is not None else not generating
    except (TypeError, ValueError):
        stable = False
    return True, bool(text), bool(text) and not generating and stable


def set_state(state: dict[str, Any], delivery_state: str, note: str) -> None:
    if delivery_state not in DELIVERY_STATES:
        raise ValueError(f"invalid delivery state: {delivery_state}")
    state["delivery_state"] = delivery_state
    state["updated_at"] = utc_now()
    state.setdefault("transitions", []).append(
        {"at": state["updated_at"], "state": delivery_state, "note": note}
    )


def identity_from_success(result: dict[str, Any]) -> tuple[str | None, str | None]:
    for row in rows(parse_json(result.get("stdout", ""))):
        conversation_id, url = conversation_identity(row)
        if conversation_id or url:
            return conversation_id, url
    return None, None


def recover_identity(
    state: dict[str, Any], state_path: Path, command_wait: int, attempts: int
) -> bool:
    known = state.get("conversation_id") or state.get("conversation_url")
    if known:
        messages = detail(state, state_path, str(known), command_wait)
        delivered, response_exists, ready = inspect_messages(messages, state["message_id"])
        if delivered:
            set_state(state, "RESPONSE_READY" if ready else "RESPONSE_PENDING", "matching MESSAGE_ID found in recorded conversation")
            state["last_successful_read_at"] = utc_now()
            if response_exists:
                state["response_observed"] = True
            return True
        return False

    before = set(state.get("pre_send_conversation_ids", []))
    for _ in range(attempts):
        candidates: list[tuple[str, str | None]] = []
        for row in history(state, state_path, command_wait):
            conversation_id, url = conversation_identity(row)
            identity = conversation_id or url
            if identity and (not conversation_id or conversation_id not in before):
                candidates.append((identity, url))

        matches: list[tuple[str, str | None, bool]] = []
        for identity, url in candidates:
            messages = detail(state, state_path, identity, command_wait)
            delivered, _, ready = inspect_messages(messages, state["message_id"])
            if delivered:
                matches.append((identity, url, ready))

        if len(matches) == 1:
            identity, url, ready = matches[0]
            state["conversation_id"] = identity
            state["conversation_url"] = url
            state["last_successful_read_at"] = utc_now()
            set_state(state, "RESPONSE_READY" if ready else "RESPONSE_PENDING", "recovered one conversation by MESSAGE_ID")
            return True
        if len(matches) > 1:
            state["duplicate_conversation_ids"] = [identity for identity, _, _ in matches]
            set_state(state, "DELIVERY_UNKNOWN", "multiple conversations contain the same MESSAGE_ID; do not resend")
            return False
    return False


def poll_response(
    state: dict[str, Any],
    state_path: Path,
    command_wait: int,
    poll_interval: int,
    total_wait: int,
) -> None:
    identity = state.get("conversation_id") or state.get("conversation_url")
    if not identity:
        return
    deadline = time.monotonic() + total_wait
    while time.monotonic() <= deadline:
        messages = detail(state, state_path, str(identity), command_wait)
        delivered, _, ready = inspect_messages(messages, state["message_id"])
        if delivered and ready:
            state["last_successful_read_at"] = utc_now()
            set_state(state, "RESPONSE_READY", "stable assistant response observed")
            return
        if delivered:
            state["last_successful_read_at"] = utc_now()
            set_state(state, "RESPONSE_PENDING", "message delivered; response not yet stable")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(poll_interval, remaining))


def read_payload(args: argparse.Namespace) -> str:
    if args.message_file:
        return Path(args.message_file).read_text(encoding="utf-8")
    if sys.stdin.isatty():
        raise ValueError("provide message content on stdin or with --message-file")
    return sys.stdin.read()


def prepare_payload(args: argparse.Namespace, body: str) -> str:
    if marker(args.message_id) in body:
        raise ValueError("message body already contains MESSAGE_ID; provide body without transport headers")
    header = (
        f"WORK_ITEM_ID: {args.work_item_id}\n"
        f"MESSAGE_ID: {args.message_id}\n"
        f"ROUND: {args.round}\n"
        f"MESSAGE_TYPE: {args.message_type}\n\n"
    )
    return header + body.lstrip("\ufeff")


def new_state(args: argparse.Namespace, state_path: Path) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "work_item_id": args.work_item_id,
        "message_id": args.message_id,
        "round": args.round,
        "message_type": args.message_type,
        "conversation_id": args.conversation,
        "conversation_url": None,
        "delivery_state": "NOT_SENT",
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "state_file": str(state_path),
        "raw_outputs": [],
        "parameters": {
            "command_wait_seconds": args.command_wait_seconds,
            "poll_interval_seconds": args.poll_interval_seconds,
            "total_response_wait_seconds": args.total_response_wait_seconds,
            "max_recovery_attempts": args.max_recovery_attempts,
        },
        "transitions": [],
    }


def output_state(state: dict[str, Any]) -> int:
    print(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True))
    if state["delivery_state"] == "RESPONSE_READY":
        return 0
    if state["delivery_state"] == "FAILED":
        return 1
    return 2


def send_command(args: argparse.Namespace) -> int:
    state_path = Path(args.state_file) if args.state_file else default_state_path(args.work_item_id, args.message_id)
    if state_path.exists():
        existing = read_json(state_path)
        if existing.get("message_id") != args.message_id:
            raise ValueError("existing state file belongs to another MESSAGE_ID")
        if existing.get("delivery_state") in NO_RESEND_STATES:
            raise ValueError(
                f"MESSAGE_ID already has state {existing['delivery_state']}; use recover, never resend"
            )

    payload = prepare_payload(args, read_payload(args))
    state = new_state(args, state_path)
    if not args.conversation:
        state["pre_send_conversation_ids"] = [
            conversation_id
            for row in history(state, state_path, args.command_wait_seconds)
            if (conversation_id := conversation_identity(row)[0])
        ]
    else:
        messages = detail(state, state_path, args.conversation, args.command_wait_seconds)
        delivered, _, ready = inspect_messages(messages, args.message_id)
        if delivered:
            set_state(state, "RESPONSE_READY" if ready else "RESPONSE_PENDING", "MESSAGE_ID already exists in target conversation; send skipped")
            write_json(state_path, state)
            return output_state(state)

    set_state(state, "SENDING", "one ask command started")
    write_json(state_path, state)
    target = ["--conversation", args.conversation] if args.conversation else ["--new"]
    result = run_opencli(
        [
            "chatgpt",
            "ask",
            payload,
            *target,
            "--timeout",
            str(args.command_wait_seconds),
            "-f",
            "json",
            "--window",
            "background",
        ],
        args.command_wait_seconds + 10,
    )
    save_raw(state, state_path, "ask", result)
    if result["timed_out"] or result["returncode"] != 0:
        set_state(state, "DELIVERY_UNKNOWN", "ask timed out or returned nonzero; recovery required before any resend")
    else:
        set_state(state, "SENT", "ask returned successfully")
        state["last_successful_write_at"] = utc_now()
        conversation_id, url = identity_from_success(result)
        state["conversation_id"] = conversation_id or state.get("conversation_id")
        state["conversation_url"] = url or state.get("conversation_url")
    write_json(state_path, state)

    recovered = recover_identity(
        state, state_path, args.command_wait_seconds, args.max_recovery_attempts
    )
    if recovered and state["delivery_state"] != "RESPONSE_READY":
        poll_response(
            state,
            state_path,
            args.command_wait_seconds,
            args.poll_interval_seconds,
            args.total_response_wait_seconds,
        )
    elif not recovered and state["delivery_state"] == "SENT" and state.get("conversation_id"):
        set_state(state, "DELIVERED", "ask returned conversation identity; response not yet observed")
        poll_response(
            state,
            state_path,
            args.command_wait_seconds,
            args.poll_interval_seconds,
            args.total_response_wait_seconds,
        )
    write_json(state_path, state)
    return output_state(state)


def recover_command(args: argparse.Namespace) -> int:
    state_path = Path(args.state_file)
    state = read_json(state_path)
    parameters = state.get("parameters", {})
    command_wait = args.command_wait_seconds or parameters.get("command_wait_seconds", COMMAND_WAIT_SECONDS)
    poll_interval = args.poll_interval_seconds or parameters.get("poll_interval_seconds", POLL_INTERVAL_SECONDS)
    total_wait = args.total_response_wait_seconds or parameters.get("total_response_wait_seconds", TOTAL_RESPONSE_WAIT_SECONDS)
    attempts = args.max_recovery_attempts or parameters.get("max_recovery_attempts", MAX_RECOVERY_ATTEMPTS)
    if state.get("delivery_state") == "FAILED":
        return output_state(state)
    recovered = recover_identity(state, state_path, command_wait, attempts)
    if recovered and state["delivery_state"] != "RESPONSE_READY":
        poll_response(state, state_path, command_wait, poll_interval, total_wait)
    if not recovered and state["delivery_state"] != "DELIVERY_UNKNOWN":
        set_state(state, "DELIVERY_UNKNOWN", "bounded recovery could not establish delivery; do not resend")
    write_json(state_path, state)
    return output_state(state)


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
    subparsers = root.add_subparsers(dest="command", required=True)

    send = subparsers.add_parser("send", help="send one MESSAGE_ID once, then recover and poll")
    send.add_argument("--work-item-id", required=True)
    send.add_argument("--message-id", required=True)
    send.add_argument("--round", required=True, type=int)
    send.add_argument("--message-type", required=True)
    send.add_argument("--conversation", help="recorded conversation ID or /c/ URL for continuation")
    send.add_argument("--message-file", help="UTF-8 body file; stdin is preferred")
    send.add_argument("--state-file", help="state path; defaults to the system temp directory")
    send.add_argument("--command-wait-seconds", type=int, default=COMMAND_WAIT_SECONDS)
    send.add_argument("--poll-interval-seconds", type=int, default=POLL_INTERVAL_SECONDS)
    send.add_argument("--total-response-wait-seconds", type=int, default=TOTAL_RESPONSE_WAIT_SECONDS)
    send.add_argument("--max-recovery-attempts", type=int, default=MAX_RECOVERY_ATTEMPTS)
    send.set_defaults(handler=send_command)

    recover = subparsers.add_parser("recover", help="recover and poll without sending")
    recover.add_argument("--state-file", required=True)
    recover.add_argument("--command-wait-seconds", type=int)
    recover.add_argument("--poll-interval-seconds", type=int)
    recover.add_argument("--total-response-wait-seconds", type=int)
    recover.add_argument("--max-recovery-attempts", type=int)
    recover.set_defaults(handler=recover_command)

    cleanup = subparsers.add_parser("cleanup", help="remove this message's system-temp evidence")
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
