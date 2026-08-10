"""Small command-line driver for one persisted ACF review-loop state."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from runtime.review_loop import (
    apply_transport_review,
    initialize_loop_state,
    mark_reviewed_state_stale,
    record_revision_applied,
    submit_review_request,
)


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

    ingest = subparsers.add_parser("ingest-review")
    ingest.add_argument("--state", required=True, type=Path)
    ingest.add_argument("--transport-state", required=True, type=Path)
    ingest.add_argument("--current-artifact-id", required=True)

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
