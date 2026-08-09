"""IDE-independent completion-gate policy used by IDE adapters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


ALLOW_STOP = "ALLOW_STOP"
CONTINUE_BOUNDED = "CONTINUE_BOUNDED"
BLOCK_AND_ESCALATE = "BLOCK_AND_ESCALATE"
SUPPORTED_PROTOCOL_VERSION = "ACF-0.1"


@dataclass(frozen=True)
class GateDecision:
    outcome: str
    reason: str
    work_item_completed: bool = False


def _criterion_identities(items: Any) -> list[str] | None:
    if not isinstance(items, list) or not items:
        return None
    identities: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            return None
        identity = item.get("CRITERION")
        if not isinstance(identity, str) or not identity or identity != identity.strip():
            return None
        identities.append(identity)
    if len(identities) != len(set(identities)):
        return None
    return identities


def _all_acceptance_met(pending: dict[str, Any], decision: dict[str, Any]) -> bool:
    agreed = _criterion_identities(pending.get("ACCEPTANCE_CRITERIA"))
    statuses = decision.get("ACCEPTANCE_STATUS")
    covered = _criterion_identities(statuses)
    return bool(
        agreed is not None
        and covered is not None
        and set(agreed) == set(covered)
        and all(item.get("STATUS") == "MET" for item in statuses)
    )


def final_approval_is_authoritative(state: dict[str, Any]) -> bool:
    """Derive approval validity from ACF fields; never trust a flat valid flag."""
    pending = state.get("PENDING_REVIEW_REQUEST")
    decision = state.get("AUTHORITATIVE_REVIEW_DECISION")
    if not isinstance(pending, dict) or not isinstance(decision, dict):
        return False
    protocol_version = state.get("PROTOCOL_VERSION")
    work_item_id = state.get("WORK_ITEM_ID")
    request_id = pending.get("REVIEW_REQUEST_ID")
    return bool(
        protocol_version
        and work_item_id
        and request_id
        and pending.get("REVIEW_KIND") == "FINAL"
        and decision.get("PROTOCOL_VERSION") == protocol_version
        and decision.get("WORK_ITEM_ID") == work_item_id
        and decision.get("IN_REPLY_TO_REVIEW_REQUEST_ID") == request_id
        and decision.get("REVIEW_KIND") == "FINAL"
        and decision.get("REVIEW_DECISION") == "APPROVE"
        and _all_acceptance_met(pending, decision)
        and decision.get("USER_DECISION_REQUIRED") in (None, False, "NONE", "")
        and state.get("UNRESOLVED_USER_DECISION") is False
        and decision.get("REVIEWED_STATE_CURRENT") is True
    )


def _pending_action(state: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]] | None:
    action = state.get("CURRENT_REQUIRED_ACTION")
    continuation = state.get("CONTINUATION_STATE")
    if not isinstance(action, dict) or not isinstance(continuation, dict):
        return None
    action_id = action.get("ACTION_ID")
    if not action_id or action.get("STATUS") != "PENDING" or continuation.get("ACTION_ID") != action_id:
        return None
    return action, continuation


def _budget_available(continuation: dict[str, Any]) -> bool:
    count = continuation.get("CONTINUATION_COUNT")
    budget = continuation.get("CONTINUATION_BUDGET")
    return bool(
        isinstance(count, int)
        and not isinstance(count, bool)
        and isinstance(budget, int)
        and not isinstance(budget, bool)
        and count >= 0
        and budget >= 0
        and count < budget
    )


def evaluate_completion_gate(state: dict[str, Any]) -> GateDecision:
    if state.get("PROTOCOL_VERSION") != SUPPORTED_PROTOCOL_VERSION:
        return GateDecision(BLOCK_AND_ESCALATE, "protocol version is unsupported or unverifiable")
    workflow_state = state.get("WORKFLOW_STATE")
    if workflow_state == "COMPLETED":
        if final_approval_is_authoritative(state):
            return GateDecision(ALLOW_STOP, "authoritative current Final APPROVE verified", True)
        return GateDecision(BLOCK_AND_ESCALATE, "COMPLETED lacks authoritative current Final APPROVE")

    if workflow_state in {"INTERMEDIATE_REVIEW_PENDING", "FINAL_REVIEW_PENDING", "WAITING_FOR_USER"}:
        return GateDecision(ALLOW_STOP, f"{workflow_state} permits idle without completion")

    pending = _pending_action(state)
    if workflow_state == "EXECUTING":
        if pending is None:
            return GateDecision(ALLOW_STOP, "no verified pending action requires continuation")
        if _budget_available(pending[1]):
            return GateDecision(CONTINUE_BOUNDED, "pending execution action and budget available")
        return GateDecision(BLOCK_AND_ESCALATE, "execution continuation budget exhausted or invalid")

    if workflow_state == "REVISION_REQUIRED":
        if pending is None:
            return GateDecision(BLOCK_AND_ESCALATE, "revision has no verified pending required action")
        if _budget_available(pending[1]):
            return GateDecision(CONTINUE_BOUNDED, "pending Browser required action and budget available")
        return GateDecision(BLOCK_AND_ESCALATE, "revision continuation budget exhausted or invalid")

    return GateDecision(BLOCK_AND_ESCALATE, "workflow state is unknown or unverifiable")


def consume_continuation(state: dict[str, Any], reason: str) -> None:
    continuation = state["CONTINUATION_STATE"]
    continuation["CONTINUATION_COUNT"] += 1
    continuation["CONTINUE_REASON"] = reason
