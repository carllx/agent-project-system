"""Small command-line driver for one persisted ACF review-loop state."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from runtime.review_loop import (
    apply_manual_review,
    apply_transport_review,
    initialize_loop_state,
    mark_reviewed_state_stale,
    record_revision_applied,
    render_browser_review_message,
    submit_review_request,
)

TRANSPORT_SCRIPT = PROJECT_ROOT / "skills" / "research-review-lead" / "scripts" / "opencli_transport.py"


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary_name, path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def output(value: dict[str, Any]) -> None:
    json.dump(value, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


def write_text_atomic(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(value)
        os.replace(temporary_name, path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def review_round(state: dict[str, Any]) -> int:
    return sum(
        1 for event in state.get("REVIEW_HISTORY", [])
        if isinstance(event, dict) and event.get("EVENT") == "REVIEW_REQUEST_SUBMITTED"
    )


def pending_request_id(state: dict[str, Any]) -> str:
    pending = state.get("PENDING_REVIEW_REQUEST")
    if not isinstance(pending, dict) or not isinstance(pending.get("REVIEW_REQUEST_ID"), str):
        raise ValueError("a pending Review Request is required")
    return pending["REVIEW_REQUEST_ID"]


def verified_continuation_target(path: Path) -> str:
    previous = load_json(path)
    target = previous.get("delivery_conversation_id")
    if (
        previous.get("delivery_state") not in {"DELIVERED", "RESPONSE_PENDING", "RESPONSE_READY"}
        or not isinstance(target, str)
        or not target
        or previous.get("target_conversation_id") != target
    ):
        raise ValueError("previous Transport state has no verified continuation target")
    return target


def run_product_transport(arguments: list[str]) -> int:
    completed = subprocess.run(
        [sys.executable, str(TRANSPORT_SCRIPT), *arguments],
        text=True,
        check=False,
    )
    return completed.returncode


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    initialize = subparsers.add_parser("initialize")
    initialize.add_argument("--contract", required=True, type=Path)
    initialize.add_argument("--state", required=True, type=Path)

    submit = subparsers.add_parser("submit-review")
    submit.add_argument("--state", required=True, type=Path)
    submit.add_argument("--request", required=True, type=Path)
    submit.add_argument("--artifact-id", required=True)

    render = subparsers.add_parser("render-review-message")
    render.add_argument("--state", required=True, type=Path)
    render.add_argument("--output", required=True, type=Path)

    send = subparsers.add_parser("send-review")
    send.add_argument("--state", required=True, type=Path)
    send.add_argument("--runtime-dir", required=True, type=Path)
    target = send.add_mutually_exclusive_group(required=True)
    target.add_argument("--prepare-new", action="store_true")
    target.add_argument("--previous-transport-state", type=Path)

    recover = subparsers.add_parser("recover-review")
    recover.add_argument("--state", required=True, type=Path)
    recover.add_argument("--transport-state", required=True, type=Path)

    ingest = subparsers.add_parser("ingest-review")
    ingest.add_argument("--state", required=True, type=Path)
    ingest.add_argument("--transport-state", required=True, type=Path)
    ingest.add_argument("--current-artifact-id", required=True)

    manual_ingest = subparsers.add_parser("ingest-manual-review")
    manual_ingest.add_argument("--state", required=True, type=Path)
    manual_ingest.add_argument("--response-file", required=True, type=Path)
    manual_ingest.add_argument("--current-artifact-id", required=True)

    revision = subparsers.add_parser("revision-applied")
    revision.add_argument("--state", required=True, type=Path)
    revision.add_argument("--evidence", required=True)

    stale = subparsers.add_parser("mark-stale")
    stale.add_argument("--state", required=True, type=Path)
    stale.add_argument("--reason", required=True)

    show = subparsers.add_parser("show")
    show.add_argument("--state", required=True, type=Path)

    args = parser.parse_args()
    if args.command == "initialize":
        if args.state.exists():
            raise FileExistsError(f"refusing to overwrite existing loop state: {args.state}")
        contract = load_json(args.contract)
        state = initialize_loop_state(
            contract["WORK_ITEM_ID"], contract["GOAL"], contract["ACCEPTANCE_CRITERIA"]
        )
        write_json_atomic(args.state, state)
        output(state)
        return 0

    state = load_json(args.state)
    if args.command == "submit-review":
        submit_review_request(state, load_json(args.request), args.artifact_id)
    elif args.command == "render-review-message":
        if args.output.exists():
            raise FileExistsError(f"refusing to overwrite canonical Browser message: {args.output}")
        write_text_atomic(args.output, render_browser_review_message(state))
        output({"message_path": str(args.output), "review_request_id": pending_request_id(state)})
        return 0
    elif args.command == "send-review":
        request_id = pending_request_id(state)
        args.runtime_dir.mkdir(parents=True, exist_ok=True)
        message_path = args.runtime_dir / f"{request_id}.message.txt"
        transport_path = args.runtime_dir / f"{request_id}.transport.json"
        if message_path.exists() or transport_path.exists():
            raise FileExistsError("review send artifacts already exist; same Request ID write is forbidden")
        write_text_atomic(message_path, render_browser_review_message(state))
        transport_arguments = [
            "send",
            "--work-item-id", state["WORK_ITEM_ID"],
            "--message-id", request_id,
            "--round", str(review_round(state)),
            "--message-type", "REVIEW_REQUEST",
            "--message-file", str(message_path),
            "--state-file", str(transport_path),
        ]
        if args.prepare_new:
            transport_arguments.append("--prepare-new")
        else:
            transport_arguments.extend([
                "--conversation", verified_continuation_target(args.previous_transport_state)
            ])
        return run_product_transport(transport_arguments)
    elif args.command == "recover-review":
        request_id = pending_request_id(state)
        transport = load_json(args.transport_state)
        if (
            transport.get("work_item_id") != state.get("WORK_ITEM_ID")
            or transport.get("message_id") != request_id
            or transport.get("send_attempt_count") != 1
        ):
            raise ValueError("Transport state is not bound to the pending one-write Review Request")
        return run_product_transport([
            "recover", "--state-file", str(args.transport_state), "--continue-pending"
        ])
    elif args.command == "ingest-review":
        result = apply_transport_review(
            state, load_json(args.transport_state), args.current_artifact_id
        )
        if not result.authoritative:
            output({
                "authoritative": False,
                "outcome": result.outcome,
                "reason": result.reason,
                "workflow_state": state.get("WORKFLOW_STATE"),
            })
            return 2
    elif args.command == "ingest-manual-review":
        raw_response_bytes = args.response_file.read_bytes()
        try:
            raw_response = raw_response_bytes.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ValueError("Manual Relay response must be strict UTF-8") from error
        result = apply_manual_review(
            state,
            raw_response,
            args.current_artifact_id,
            raw_response_path=str(args.response_file.resolve()),
            raw_response_sha256=hashlib.sha256(raw_response_bytes).hexdigest(),
        )
        if not result.authoritative:
            output({
                "authoritative": False,
                "outcome": result.outcome,
                "reason": result.reason,
                "review_source": "MANUAL_RELAY",
                "workflow_state": state.get("WORKFLOW_STATE"),
            })
            return 2
    elif args.command == "revision-applied":
        record_revision_applied(state, args.evidence)
    elif args.command == "mark-stale":
        mark_reviewed_state_stale(state, args.reason)
    elif args.command == "show":
        output(state)
        return 0
    write_json_atomic(args.state, state)
    output(state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
