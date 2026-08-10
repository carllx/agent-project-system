"""Minimal IDE-independent ACF review-loop state bridge.

This module deliberately does not send Browser messages or translate IDE lifecycle
events.  It consumes only an identity-verified RR transport result, maps it to an
ACF-0.1 Decision, and advances the Product workflow through the completion gate.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from typing import Any

from runtime.completion_gate import evaluate_completion_gate, final_approval_is_authoritative


SUPPORTED_PROTOCOL_VERSION = "ACF-0.1"
PENDING_BY_KIND = {
    "INTERMEDIATE": "INTERMEDIATE_REVIEW_PENDING",
    "FINAL": "FINAL_REVIEW_PENDING",
}
DECISION_MAP = {
    "APPROVE": "APPROVE",
    "PASS": "APPROVE",
    "PASS_WITH_DEBT": "APPROVE",
    "REVISE": "REVISE",
    "ESCALATE": "ESCALATE_TO_USER",
    "ESCALATE_TO_USER": "ESCALATE_TO_USER",
}
ACCEPTANCE_STATUSES = {"MET", "NOT_MET", "UNVERIFIED"}
NONE_VALUES = {"", "NONE", "NO", "FALSE", "N/A", "NOT_APPLICABLE"}


@dataclass(frozen=True)
class TransitionResult:
    authoritative: bool
    outcome: str
    reason: str


def initialize_loop_state(
    work_item_id: str,
    goal: str,
    acceptance_criteria: list[dict[str, Any]],
) -> dict[str, Any]:
    criteria = _normalized_criteria(acceptance_criteria)
    if not work_item_id or not goal or criteria is None:
        raise ValueError("work item, goal, and unique acceptance criteria are required")
    return {
        "PROTOCOL_VERSION": SUPPORTED_PROTOCOL_VERSION,
        "WORK_ITEM_ID": work_item_id,
        "GOAL": goal,
        "ACCEPTANCE_CRITERIA": criteria,
        "WORKFLOW_STATE": "EXECUTING",
        "UNRESOLVED_USER_DECISION": False,
        "PENDING_REVIEW_REQUEST": None,
        "PENDING_REVIEWED_ARTIFACT_ID": None,
        "AUTHORITATIVE_REVIEW_DECISION": None,
        "CURRENT_REQUIRED_ACTION": None,
        "REQUIRED_ACTIONS": [],
        "CONTINUATION_STATE": None,
        "REQUIRED_RESUBMISSION_KIND": None,
        "USED_REVIEW_REQUEST_IDS": [],
        "REVIEW_HISTORY": [],
    }


def submit_review_request(
    state: dict[str, Any],
    request: dict[str, Any],
    reviewed_artifact_id: str,
) -> None:
    if state.get("WORKFLOW_STATE") != "EXECUTING":
        raise ValueError("a Review Request may be submitted only from EXECUTING")
    if not reviewed_artifact_id or reviewed_artifact_id != reviewed_artifact_id.strip():
        raise ValueError("a stable reviewed artifact identity is required")
    if request.get("PROTOCOL_VERSION") != state.get("PROTOCOL_VERSION"):
        raise ValueError("Review Request Protocol mismatch")
    if request.get("WORK_ITEM_ID") != state.get("WORK_ITEM_ID"):
        raise ValueError("Review Request Work Item mismatch")
    if request.get("GOAL") != state.get("GOAL"):
        raise ValueError("Review Request Goal must match the current Goal")
    for field in ("CURRENT_TASK", "CHANGES", "EVIDENCE"):
        if field not in request or not _is_explicit_value(request[field]):
            raise ValueError(f"Review Request field is required: {field}")
    assessment = request.get("EXECUTION_ASSESSMENT")
    assessment_fields = {
        "CLAIMED_STATUS", "KNOWN_RISKS", "UNVERIFIED", "OPEN_QUESTIONS", "PROPOSED_NEXT_ACTION"
    }
    if (
        not isinstance(assessment, dict)
        or not assessment_fields.issubset(assessment)
        or any(not _is_explicit_value(assessment[field]) for field in assessment_fields)
        or assessment.get("CLAIMED_STATUS") not in {"IN_PROGRESS", "CLAIM_READY_FOR_REVIEW"}
    ):
        raise ValueError("Review Request Execution Assessment is incomplete")
    request_id = request.get("REVIEW_REQUEST_ID")
    if not isinstance(request_id, str) or not request_id or request_id in state["USED_REVIEW_REQUEST_IDS"]:
        raise ValueError("Review Request ID must be nonempty and unique")
    kind = request.get("REVIEW_KIND")
    if kind not in PENDING_BY_KIND:
        raise ValueError("unsupported Review Kind")
    required_kind = state.get("REQUIRED_RESUBMISSION_KIND")
    if required_kind and kind != required_kind:
        raise ValueError("review after REVISE must preserve Review Kind")
    if kind == "FINAL" and (
        request.get("REVIEW_TRIGGER") != "READY_FOR_COMPLETION"
        or assessment.get("CLAIMED_STATUS") != "CLAIM_READY_FOR_REVIEW"
    ):
        raise ValueError("Final Review requires READY_FOR_COMPLETION and CLAIM_READY_FOR_REVIEW")
    requested_criteria = _normalized_criteria(request.get("ACCEPTANCE_CRITERIA"))
    agreed = _normalized_criteria(state.get("ACCEPTANCE_CRITERIA"))
    if requested_criteria is None or agreed is None or requested_criteria != agreed:
        raise ValueError("Review Request must exactly snapshot every agreed Acceptance Criterion")

    snapshot = copy.deepcopy(request)
    snapshot["ACCEPTANCE_CRITERIA"] = requested_criteria
    state["PENDING_REVIEW_REQUEST"] = snapshot
    state["PENDING_REVIEWED_ARTIFACT_ID"] = reviewed_artifact_id
    state["AUTHORITATIVE_REVIEW_DECISION"] = None
    state["WORKFLOW_STATE"] = PENDING_BY_KIND[kind]
    state["USED_REVIEW_REQUEST_IDS"].append(request_id)
    state["REQUIRED_RESUBMISSION_KIND"] = None
    if isinstance(state.get("CURRENT_REQUIRED_ACTION"), dict) and state["CURRENT_REQUIRED_ACTION"].get("STATUS") == "APPLIED":
        state["CURRENT_REQUIRED_ACTION"] = None
        state["CONTINUATION_STATE"] = None
        state["REQUIRED_ACTIONS"] = []
    state["REVIEW_HISTORY"].append({
        "EVENT": "REVIEW_REQUEST_SUBMITTED",
        "REVIEW_REQUEST_ID": request_id,
        "REVIEW_KIND": kind,
        "REVIEWED_ARTIFACT_ID": reviewed_artifact_id,
    })


def apply_transport_review(
    state: dict[str, Any],
    transport_state: dict[str, Any],
    current_artifact_id: str,
) -> TransitionResult:
    """Apply one identity-verified RR response; ignore Transport completion labels."""
    pending = state.get("PENDING_REVIEW_REQUEST")
    expected_pending = PENDING_BY_KIND.get(pending.get("REVIEW_KIND")) if isinstance(pending, dict) else None
    if expected_pending is None or state.get("WORKFLOW_STATE") != expected_pending:
        return TransitionResult(False, "NON_AUTHORITATIVE", "no matching pending Review Request")
    if (
        transport_state.get("official_response_eligible") is not True
        or transport_state.get("response_identity_status") != "RESPONSE_IDENTITY_VERIFIED"
        or transport_state.get("work_item_id") != state.get("WORK_ITEM_ID")
        or transport_state.get("message_id") != pending.get("REVIEW_REQUEST_ID")
    ):
        return TransitionResult(False, "NON_AUTHORITATIVE", "Transport response identity is not verified")
    review = transport_state.get("verified_rr_review")
    if not isinstance(review, dict):
        return TransitionResult(False, "NON_AUTHORITATIVE", "verified RR review is missing")
    try:
        decision = rr_review_to_acf_decision(
            review,
            reviewed_state_current=(
                bool(current_artifact_id)
                and current_artifact_id == state.get("PENDING_REVIEWED_ARTIFACT_ID")
            ),
        )
    except ValueError as exc:
        return TransitionResult(False, "NON_AUTHORITATIVE", str(exc))
    return apply_review_decision(state, decision)


def apply_review_decision(
    state: dict[str, Any], decision: dict[str, Any]
) -> TransitionResult:
    pending = state.get("PENDING_REVIEW_REQUEST")
    expected_pending = PENDING_BY_KIND.get(pending.get("REVIEW_KIND")) if isinstance(pending, dict) else None
    if expected_pending is None or state.get("WORKFLOW_STATE") != expected_pending:
        return TransitionResult(False, "NON_AUTHORITATIVE", "no matching pending Review Request")
    if not _binding_matches(state, pending, decision):
        return TransitionResult(False, "NON_AUTHORITATIVE", "Decision binding does not match pending Request")
    statuses = _normalized_statuses(decision.get("ACCEPTANCE_STATUS"))
    if statuses is None or _criterion_ids(statuses) != _criterion_ids(pending.get("ACCEPTANCE_CRITERIA")):
        return TransitionResult(False, "NON_AUTHORITATIVE", "Acceptance coverage is malformed or incomplete")
    decision = copy.deepcopy(decision)
    decision["ACCEPTANCE_STATUS"] = statuses
    review_decision = decision.get("REVIEW_DECISION")
    trigger = pending.get("REVIEW_TRIGGER")
    if trigger in {"USER_DECISION_REQUIRED", "SCOPE_CHANGE"} and review_decision != "ESCALATE_TO_USER":
        return TransitionResult(False, "NON_AUTHORITATIVE", "User-authority trigger requires escalation")

    if review_decision == "REVISE":
        actions = decision.get("REQUIRED_ACTIONS")
        if not isinstance(actions, list) or not actions or any(not isinstance(item, str) or not item.strip() for item in actions):
            return TransitionResult(False, "NON_AUTHORITATIVE", "REVISE requires executable Required Actions")
        action_id = f"{pending['REVIEW_REQUEST_ID']}-ACTION-1"
        state["AUTHORITATIVE_REVIEW_DECISION"] = decision
        state["REQUIRED_ACTIONS"] = [item.strip() for item in actions]
        state["CURRENT_REQUIRED_ACTION"] = {
            "ACTION_ID": action_id,
            "DESCRIPTION": "\n".join(state["REQUIRED_ACTIONS"]),
            "STATUS": "PENDING",
        }
        state["CONTINUATION_STATE"] = {
            "ACTION_ID": action_id,
            "CONTINUATION_COUNT": 0,
            "CONTINUATION_BUDGET": 1,
            "CONTINUE_REASON": "Browser Final REVISE requires revision",
        }
        state["REQUIRED_RESUBMISSION_KIND"] = pending["REVIEW_KIND"]
        state["WORKFLOW_STATE"] = "REVISION_REQUIRED"
        _record_decision(state, decision)
        return TransitionResult(True, "REVISION_REQUIRED", "authoritative REVISE applied")

    if review_decision == "ESCALATE_TO_USER":
        if _is_none(decision.get("USER_DECISION_REQUIRED")):
            return TransitionResult(False, "NON_AUTHORITATIVE", "escalation requires an explicit User Decision")
        state["AUTHORITATIVE_REVIEW_DECISION"] = decision
        state["UNRESOLVED_USER_DECISION"] = True
        state["WORKFLOW_STATE"] = "WAITING_FOR_USER"
        _record_decision(state, decision)
        return TransitionResult(True, "WAITING_FOR_USER", "authoritative escalation applied")

    if review_decision != "APPROVE":
        return TransitionResult(False, "NON_AUTHORITATIVE", "unsupported Review Decision")
    if decision.get("REQUIRED_ACTIONS") or not _is_none(decision.get("USER_DECISION_REQUIRED")):
        return TransitionResult(False, "NON_AUTHORITATIVE", "APPROVE cannot carry Required Actions or a User Decision")
    if pending["REVIEW_KIND"] == "INTERMEDIATE":
        state["AUTHORITATIVE_REVIEW_DECISION"] = decision
        state["PENDING_REVIEW_REQUEST"] = None
        state["PENDING_REVIEWED_ARTIFACT_ID"] = None
        state["WORKFLOW_STATE"] = "EXECUTING"
        _record_decision(state, decision)
        return TransitionResult(True, "EXECUTING", "Intermediate APPROVE permits continued execution")

    state["AUTHORITATIVE_REVIEW_DECISION"] = decision
    if not final_approval_is_authoritative(state):
        state["AUTHORITATIVE_REVIEW_DECISION"] = None
        return TransitionResult(False, "NON_AUTHORITATIVE", "Final APPROVE failed Completion Authority checks")
    state["WORKFLOW_STATE"] = "COMPLETED"
    gate = evaluate_completion_gate(state)
    if not gate.work_item_completed:
        state["WORKFLOW_STATE"] = expected_pending
        state["AUTHORITATIVE_REVIEW_DECISION"] = None
        return TransitionResult(False, "NON_AUTHORITATIVE", "Completion Gate rejected Final APPROVE")
    _record_decision(state, decision)
    return TransitionResult(True, "COMPLETED", gate.reason)


def record_revision_applied(state: dict[str, Any], evidence: str) -> None:
    if state.get("WORKFLOW_STATE") != "REVISION_REQUIRED":
        raise ValueError("no revision is pending")
    action = state.get("CURRENT_REQUIRED_ACTION")
    if not isinstance(action, dict) or action.get("STATUS") != "PENDING" or not evidence:
        raise ValueError("pending action and revision Evidence are required")
    action["STATUS"] = "APPLIED"
    action["EVIDENCE"] = evidence
    state["WORKFLOW_STATE"] = "EXECUTING"
    state["AUTHORITATIVE_REVIEW_DECISION"] = None
    state["PENDING_REVIEW_REQUEST"] = None
    state["PENDING_REVIEWED_ARTIFACT_ID"] = None
    state["REVIEW_HISTORY"].append({
        "EVENT": "REQUIRED_ACTION_APPLIED",
        "ACTION_ID": action["ACTION_ID"],
        "EVIDENCE": evidence,
    })


def mark_reviewed_state_stale(state: dict[str, Any], reason: str) -> None:
    """Invalidate a reviewed snapshot after a material change."""
    if not reason:
        raise ValueError("stale reason is required")
    decision = state.get("AUTHORITATIVE_REVIEW_DECISION")
    if isinstance(decision, dict):
        decision["REVIEWED_STATE_CURRENT"] = False
    pending = state.get("PENDING_REVIEW_REQUEST")
    pending_kind = pending.get("REVIEW_KIND") if isinstance(pending, dict) else None
    state["PENDING_REVIEW_REQUEST"] = None
    state["PENDING_REVIEWED_ARTIFACT_ID"] = None
    state["AUTHORITATIVE_REVIEW_DECISION"] = None
    if state.get("WORKFLOW_STATE") in {
        "INTERMEDIATE_REVIEW_PENDING", "FINAL_REVIEW_PENDING", "COMPLETED"
    }:
        state["WORKFLOW_STATE"] = "EXECUTING"
    if pending_kind in PENDING_BY_KIND:
        state["REQUIRED_RESUBMISSION_KIND"] = pending_kind
    state["REVIEW_HISTORY"].append({"EVENT": "REVIEWED_STATE_INVALIDATED", "REASON": reason})


def rr_review_to_acf_decision(
    review: dict[str, Any], *, reviewed_state_current: bool
) -> dict[str, Any]:
    """Map the existing strict RR envelope to the ACF-0.1 Decision contract.

    ACF identity fields that the frozen RR parser does not expose at top level are
    carried inside its existing VALIDATION field as one exact compatibility block.
    """
    binding = _parse_acf_binding(review.get("VALIDATION"))
    reply_id = review.get("IN_REPLY_TO_MESSAGE_ID")
    if binding.get("IN_REPLY_TO_REVIEW_REQUEST_ID") != reply_id:
        raise ValueError("wire and ACF reply identities do not match")
    raw_decision = str(review.get("REVIEW_DECISION") or "").strip()
    mapped = DECISION_MAP.get(raw_decision)
    if mapped is None:
        raise ValueError("unsupported wire Review Decision")
    if mapped == "APPROVE" and not _is_none(review.get("BLOCKERS")):
        raise ValueError("APPROVE cannot carry a blocking wire finding")
    statuses = _parse_acceptance_status_text(review.get("ACCEPTANCE_STATUS"))
    required_actions = []
    next_work_order = str(review.get("NEXT_WORK_ORDER") or "").strip()
    if not _is_none(next_work_order):
        required_actions = [next_work_order]
    return {
        "PROTOCOL_VERSION": binding["PROTOCOL_VERSION"],
        "WORK_ITEM_ID": review.get("WORK_ITEM_ID"),
        "IN_REPLY_TO_REVIEW_REQUEST_ID": binding["IN_REPLY_TO_REVIEW_REQUEST_ID"],
        "REVIEW_KIND": binding["REVIEW_KIND"],
        "REVIEW_DECISION": mapped,
        "ACCEPTANCE_STATUS": statuses,
        "FINDINGS": review.get("FINDINGS", "NONE"),
        "REQUIRED_ACTIONS": required_actions,
        "DEBT": review.get("DEBT", "NONE"),
        "USER_DECISION_REQUIRED": review.get("USER_DECISION_REQUIRED", "NONE"),
        "REVIEWED_STATE_CURRENT": reviewed_state_current,
    }


def _parse_acf_binding(value: Any) -> dict[str, str]:
    if not isinstance(value, str):
        raise ValueError("ACF binding block is missing")
    lines = [line.strip() for line in value.splitlines() if line.strip()]
    if len(lines) != 5 or lines[0] != "ACF_BINDING_BEGIN" or lines[-1] != "ACF_BINDING_END":
        raise ValueError("ACF binding block is malformed")
    fields: dict[str, str] = {}
    for line in lines[1:-1]:
        match = re.fullmatch(r"([A-Z][A-Z0-9_]*):\s*(\S.*)", line)
        if not match or match.group(1) in fields:
            raise ValueError("ACF binding field is malformed or duplicated")
        fields[match.group(1)] = match.group(2).strip()
    expected = {"PROTOCOL_VERSION", "IN_REPLY_TO_REVIEW_REQUEST_ID", "REVIEW_KIND"}
    if set(fields) != expected:
        raise ValueError("ACF binding fields are incomplete")
    return fields


def _parse_acceptance_status_text(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Acceptance Status is missing")
    items: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for raw_line in value.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        criterion = re.fullmatch(r"-?\s*CRITERION:\s*(\S.*)", line)
        status = re.fullmatch(r"STATUS:\s*(MET|NOT_MET|UNVERIFIED)", line)
        evidence = re.fullmatch(r"EVIDENCE:\s*(.*)", line)
        if criterion:
            if current is not None:
                items.append(current)
            current = {"CRITERION": criterion.group(1).strip()}
        elif status and current is not None and "STATUS" not in current:
            current["STATUS"] = status.group(1)
        elif evidence and current is not None and "EVIDENCE" not in current:
            current["EVIDENCE"] = evidence.group(1).strip() or "NONE"
        else:
            raise ValueError("Acceptance Status is malformed")
    if current is not None:
        items.append(current)
    normalized = _normalized_statuses(items)
    if normalized is None:
        raise ValueError("Acceptance Status is malformed or ambiguous")
    return normalized


def _normalized_criteria(value: Any) -> list[dict[str, Any]] | None:
    if not isinstance(value, list) or not value:
        return None
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            return None
        identity = item.get("CRITERION")
        if not isinstance(identity, str) or not identity or identity != identity.strip() or identity in seen:
            return None
        seen.add(identity)
        result.append(copy.deepcopy(item))
    return result


def _normalized_statuses(value: Any) -> list[dict[str, Any]] | None:
    result = _normalized_criteria(value)
    if result is None or any(
        item.get("STATUS") not in ACCEPTANCE_STATUSES
        or not isinstance(item.get("EVIDENCE"), str)
        or not item["EVIDENCE"].strip()
        or (item.get("STATUS") == "MET" and _is_none(item["EVIDENCE"]))
        for item in result
    ):
        return None
    return result


def _criterion_ids(items: Any) -> set[str] | None:
    normalized = _normalized_criteria(items)
    return {item["CRITERION"] for item in normalized} if normalized is not None else None


def _binding_matches(
    state: dict[str, Any], pending: dict[str, Any], decision: dict[str, Any]
) -> bool:
    return bool(
        decision.get("PROTOCOL_VERSION") == state.get("PROTOCOL_VERSION")
        and decision.get("WORK_ITEM_ID") == state.get("WORK_ITEM_ID")
        and decision.get("IN_REPLY_TO_REVIEW_REQUEST_ID") == pending.get("REVIEW_REQUEST_ID")
        and decision.get("REVIEW_KIND") == pending.get("REVIEW_KIND")
    )


def _record_decision(state: dict[str, Any], decision: dict[str, Any]) -> None:
    state["REVIEW_HISTORY"].append({
        "EVENT": "AUTHORITATIVE_REVIEW_DECISION_APPLIED",
        "REVIEW_REQUEST_ID": decision["IN_REPLY_TO_REVIEW_REQUEST_ID"],
        "REVIEW_KIND": decision["REVIEW_KIND"],
        "REVIEW_DECISION": decision["REVIEW_DECISION"],
    })


def _is_none(value: Any) -> bool:
    if value is None or value is False:
        return True
    return isinstance(value, str) and value.strip().upper() in NONE_VALUES


def _is_explicit_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return isinstance(value, (list, dict))
