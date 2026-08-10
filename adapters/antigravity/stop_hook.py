"""Antigravity Stop Hook translation for the ACF completion-gate policy."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from runtime.completion_gate import ALLOW_STOP, BLOCK_AND_ESCALATE, CONTINUE_BOUNDED
from runtime.completion_gate import consume_continuation, evaluate_completion_gate

ADAPTER_VERSION = "AG-CG-0.1"


def _normalized_path(value: str) -> str:
    return os.path.normcase(os.path.abspath(os.path.normpath(value)))


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary_name, path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def _matching_route(config: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any] | None:
    payload_paths = {
        _normalized_path(item)
        for item in payload.get("workspacePaths", [])
        if isinstance(item, str) and item
    }
    conversation_id = payload.get("conversationId")
    matches: list[dict[str, Any]] = []
    for route in config.get("routes", []):
        if not isinstance(route, dict) or not isinstance(route.get("workspace_path"), str):
            continue
        if _normalized_path(route["workspace_path"]) not in payload_paths:
            continue
        configured_conversation = route.get("conversation_id")
        if configured_conversation and configured_conversation != conversation_id:
            continue
        matches.append(route)
    return matches[0] if len(matches) == 1 else None


def _append_evidence(path: Path | None, record: dict[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _runtime_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: payload.get(key) for key in (
        "conversationId", "workspacePaths", "executionNum", "terminationReason", "fullyIdle"
    )}


def handle_stop(config_path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    config = _load_json(config_path)
    if config.get("adapter_version") != ADAPTER_VERSION:
        return {"decision": "ignore", "reason": "unsupported or missing adapter version"}
    route = _matching_route(config, payload)
    if route is None:
        return {"decision": "ignore", "reason": "no unique configured ACF route matched"}

    try:
        state_path = Path(route["state_path"])
        evidence_path = Path(route["evidence_path"]) if route.get("evidence_path") else None
        state = _load_json(state_path)
    except (KeyError, OSError, ValueError, json.JSONDecodeError) as exc:
        return {"decision": "stop", "reason": f"BLOCK_AND_ESCALATE: invalid route state: {type(exc).__name__}"}
    if not route.get("work_item_id") or state.get("WORK_ITEM_ID") != route.get("work_item_id"):
        return {"decision": "stop", "reason": "BLOCK_AND_ESCALATE: route Work Item mismatch"}
    gate_decision = evaluate_completion_gate(state)
    if gate_decision.outcome == CONTINUE_BOUNDED:
        consume_continuation(state, gate_decision.reason)
        _write_json_atomic(state_path, state)

    _append_evidence(evidence_path, {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "adapter_version": config.get("adapter_version"),
        "protocol_version": state.get("PROTOCOL_VERSION"),
        "work_item_id": state.get("WORK_ITEM_ID"),
        "workflow_state": state.get("WORKFLOW_STATE"),
        "current_required_action": state.get("CURRENT_REQUIRED_ACTION"),
        "continuation_state": state.get("CONTINUATION_STATE"),
        "adapter_outcome": gate_decision.outcome,
        "reason": gate_decision.reason,
        "work_item_completed": gate_decision.work_item_completed,
        "stop_runtime_metadata": _runtime_metadata(payload),
    })

    if gate_decision.outcome == CONTINUE_BOUNDED:
        action = state.get("CURRENT_REQUIRED_ACTION")
        action_description = (
            action.get("DESCRIPTION") if isinstance(action, dict) else None
        )
        reason = gate_decision.reason
        if isinstance(action_description, str) and action_description.strip():
            reason = f"{reason}; REQUIRED_ACTION: {action_description.strip()}"
        return {"decision": "continue", "reason": reason}
    if gate_decision.outcome in {ALLOW_STOP, BLOCK_AND_ESCALATE}:
        return {"decision": "stop", "reason": gate_decision.reason}
    return {"decision": "ignore", "reason": "unsupported adapter outcome"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args()
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("Stop stdin must be a JSON object")
        response = handle_stop(args.config, payload)
    except Exception as exc:
        response = {"decision": "ignore", "reason": f"adapter input/config failure: {type(exc).__name__}"}
    json.dump(response, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
