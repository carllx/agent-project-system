import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from runtime.completion_gate import ALLOW_STOP, CONTINUE_BOUNDED, evaluate_completion_gate
from runtime.review_loop import (
    apply_review_decision,
    apply_transport_review,
    initialize_loop_state,
    mark_reviewed_state_stale,
    record_revision_applied,
    render_browser_review_message,
    submit_review_request,
)
from scripts import acf_review_loop
from scripts.test_opencli_transport import TRANSPORT_MODULE


WORK_ITEM_ID = "REAL-LOOP-001"
ROOT = Path(__file__).resolve().parents[1]
ACCEPTANCE_CRITERIA = [
    {"CRITERION": "AC1", "DESCRIPTION": "artifact is correct"},
    {"CRITERION": "AC2", "DESCRIPTION": "tests pass"},
]


def loop_state():
    return initialize_loop_state(WORK_ITEM_ID, "exercise one real two-round review", ACCEPTANCE_CRITERIA)


def final_request(request_id):
    return {
        "PROTOCOL_VERSION": "ACF-0.1",
        "WORK_ITEM_ID": WORK_ITEM_ID,
        "REVIEW_REQUEST_ID": request_id,
        "REVIEW_KIND": "FINAL",
        "REVIEW_TRIGGER": "READY_FOR_COMPLETION",
        "GOAL": "exercise one real two-round review",
        "ACCEPTANCE_CRITERIA": copy.deepcopy(ACCEPTANCE_CRITERIA),
        "CURRENT_TASK": "review the current artifact",
        "CHANGES": ["bounded artifact change"],
        "EVIDENCE": ["commit identity", "test result"],
        "EXECUTION_ASSESSMENT": {
            "CLAIMED_STATUS": "CLAIM_READY_FOR_REVIEW",
            "KNOWN_RISKS": "NONE",
            "UNVERIFIED": "NONE",
            "OPEN_QUESTIONS": "NONE",
            "PROPOSED_NEXT_ACTION": "Browser Final Review",
        },
    }


def acceptance_text(ac2_status="MET"):
    return "\n".join((
        "- CRITERION: AC1",
        "  STATUS: MET",
        "  EVIDENCE: artifact diff",
        "- CRITERION: AC2",
        f"  STATUS: {ac2_status}",
        "  EVIDENCE: test output" if ac2_status == "MET" else "  EVIDENCE: missing case",
    ))


def rr_review(request_id, decision, *, ac2_status="MET", next_work_order="NONE", validation=None):
    return {
        "WORK_ITEM_ID": WORK_ITEM_ID,
        "IN_REPLY_TO_MESSAGE_ID": request_id,
        "ROUND": "1",
        "REVIEW_DECISION": decision,
        "WORK_ITEM_STATE": "ACHIEVED",
        "ACCEPTANCE_STATUS": acceptance_text(ac2_status),
        "FINDINGS": "AC2 needs a regression" if ac2_status != "MET" else "NONE",
        "BLOCKERS": "NONE",
        "DEBT": "NONE",
        "NEXT_WORK_ORDER": next_work_order,
        "VALIDATION": validation or "\n".join((
            "ACF_BINDING_BEGIN",
            "PROTOCOL_VERSION: ACF-0.1",
            f"IN_REPLY_TO_REVIEW_REQUEST_ID: {request_id}",
            "REVIEW_KIND: FINAL",
            "ACF_BINDING_END",
        )),
        "USER_DECISION_REQUIRED": "NONE",
    }


def transport_state(request_id, review):
    return {
        "work_item_id": WORK_ITEM_ID,
        "message_id": request_id,
        "official_response_eligible": True,
        "response_identity_status": "RESPONSE_IDENTITY_VERIFIED",
        "verified_rr_review": review,
        # A frozen Transport label is not Product Completion Authority.
        "work_item_state": "ACHIEVED",
    }


class RealAgentReviewLoopTests(unittest.TestCase):
    def test_canonical_browser_message_is_deterministic_and_complete(self):
        state = loop_state()
        request_id = f"{WORK_ITEM_ID}-CANONICAL-R1-FINAL"
        request = final_request(request_id)
        request["EVIDENCE"].append("source syntax: value < limit | fallback & audit ^ proof % complete")
        submit_review_request(state, request, "artifact-1")
        first = render_browser_review_message(state)
        second = render_browser_review_message(copy.deepcopy(state))
        self.assertEqual(first, second)
        self.assertIn("STRICT_BROWSER_RESPONSE_CONTRACT", first)
        self.assertIn(f"IN_REPLY_TO_MESSAGE_ID: {request_id}", first)
        self.assertIn(f"IN_REPLY_TO_REVIEW_REQUEST_ID: {request_id}", first)
        self.assertIn("CRITERION: AC1", first)
        self.assertIn("CRITERION: AC2", first)
        self.assertIn("\n- CRITERION: AC1\n  STATUS:", first)
        self.assertNotIn("\nCRITERION: AC1\nSTATUS:", first)
        self.assertIn("VALIDATION:\n  ACF_BINDING_BEGIN\n  PROTOCOL_VERSION:", first)
        self.assertIn("APPROVE, REVISE, ESCALATE_TO_USER", first)
        self.assertIn("Do not infer a required decision", first)
        for metacharacter in "<>|&^%":
            self.assertNotIn(metacharacter, first)
        self.assertIn("\\u003c", first)
        self.assertIn("\\u007c", first)

    def test_canonical_wire_shape_is_accepted_by_frozen_transport_parser(self):
        request_id = f"{WORK_ITEM_ID}-WIRE-SHAPE-R1-FINAL"
        response = "\n".join((
            "RR_REVIEW_BEGIN",
            f"WORK_ITEM_ID: {WORK_ITEM_ID}",
            f"IN_REPLY_TO_MESSAGE_ID: {request_id}",
            "ROUND: 1",
            "REVIEW_DECISION: REVISE",
            "WORK_ITEM_STATE: IN_PROGRESS",
            "ACCEPTANCE_STATUS:",
            "- CRITERION: AC1",
            "  STATUS: MET",
            "  EVIDENCE: artifact diff",
            "- CRITERION: AC2",
            "  STATUS: NOT_MET",
            "  EVIDENCE: missing regression",
            "FINDINGS: AC2 is missing",
            "BLOCKERS: AC2 is missing",
            "DEBT: NONE",
            "NEXT_WORK_ORDER: add the AC2 regression",
            "VALIDATION:",
            "  ACF_BINDING_BEGIN",
            "  PROTOCOL_VERSION: ACF-0.1",
            f"  IN_REPLY_TO_REVIEW_REQUEST_ID: {request_id}",
            "  REVIEW_KIND: FINAL",
            "  ACF_BINDING_END",
            "USER_DECISION_REQUIRED: NONE",
            "RR_REVIEW_END",
        ))
        parsed = TRANSPORT_MODULE.rr_response_fields(
            response,
            expected_message_id=request_id,
            expected_work_item_id=WORK_ITEM_ID,
            expected_round=1,
        )
        self.assertNotIn("PROTOCOL_ERROR", parsed)
        self.assertNotIn("REPLY_IDENTITY_ERROR", parsed)
        self.assertIn("ACF_BINDING_BEGIN", parsed["VALIDATION"])
        self.assertIn("CRITERION: AC2", parsed["ACCEPTANCE_STATUS"])

    def test_canonical_browser_message_passes_transport_preflight(self):
        state = loop_state()
        request_id = f"{WORK_ITEM_ID}-PREFLIGHT-R1-FINAL"
        submit_review_request(state, final_request(request_id), "artifact-1")
        body = render_browser_review_message(state)
        args = type("Args", (), {
            "work_item_id": WORK_ITEM_ID,
            "message_id": request_id,
            "round": 1,
            "message_type": "REVIEW_REQUEST",
        })()
        payload = TRANSPORT_MODULE.prepare_payload(args, body)
        packet = json.loads(payload)
        self.assertEqual(packet["MESSAGE_ID"], request_id)
        self.assertIn(f"IN_REPLY_TO_MESSAGE_ID: {request_id}", packet["EVIDENCE"])

    def test_send_review_uses_one_fail_closed_canonical_path(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary_directory:
            directory = Path(temporary_directory)
            state = loop_state()
            request_id = f"{WORK_ITEM_ID}-SEND-R1-FINAL"
            submit_review_request(state, final_request(request_id), "artifact-1")
            state_path = directory / "loop-state.json"
            state_path.write_text(json.dumps(state), encoding="utf-8")
            runtime_dir = directory / "round-1"
            argv = [
                "acf_review_loop.py", "send-review", "--state", str(state_path),
                "--runtime-dir", str(runtime_dir), "--prepare-new",
            ]
            with mock.patch.object(sys, "argv", argv), mock.patch.object(
                acf_review_loop, "run_product_transport", return_value=0
            ) as transport:
                self.assertEqual(acf_review_loop.main(), 0)
            arguments = transport.call_args.args[0]
            self.assertEqual(arguments.count("send"), 1)
            self.assertIn("--prepare-new", arguments)
            self.assertIn(request_id, arguments)
            self.assertFalse(any("budget" in item or item.startswith("--max-") for item in arguments))
            message_path = runtime_dir / f"{request_id}.message.txt"
            self.assertEqual(message_path.read_text(encoding="utf-8"), render_browser_review_message(state))
            with mock.patch.object(sys, "argv", argv), mock.patch.object(
                acf_review_loop, "run_product_transport", return_value=0
            ) as second_transport:
                with self.assertRaisesRegex(FileExistsError, "same Request ID write is forbidden"):
                    acf_review_loop.main()
                second_transport.assert_not_called()

    def test_send_review_derives_verified_continuation_target(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary_directory:
            directory = Path(temporary_directory)
            state = loop_state()
            request_id = f"{WORK_ITEM_ID}-SEND-R2-FINAL"
            submit_review_request(state, final_request(request_id), "artifact-2")
            state_path = directory / "loop-state.json"
            state_path.write_text(json.dumps(state), encoding="utf-8")
            conversation_id = "conversation-a"
            previous_path = directory / "round-1.transport.json"
            previous_path.write_text(json.dumps({
                "delivery_state": "RESPONSE_READY",
                "delivery_conversation_id": conversation_id,
                "target_conversation_id": conversation_id,
            }), encoding="utf-8")
            argv = [
                "acf_review_loop.py", "send-review", "--state", str(state_path),
                "--runtime-dir", str(directory / "round-2"),
                "--previous-transport-state", str(previous_path),
            ]
            with mock.patch.object(sys, "argv", argv), mock.patch.object(
                acf_review_loop, "run_product_transport", return_value=0
            ) as transport:
                self.assertEqual(acf_review_loop.main(), 0)
            arguments = transport.call_args.args[0]
            self.assertNotIn("--prepare-new", arguments)
            self.assertEqual(arguments[arguments.index("--conversation") + 1], conversation_id)

    def test_full_final_revise_revision_final_approve_loop(self):
        state = loop_state()
        first_id = f"{WORK_ITEM_ID}-E2E-R1-FINAL"
        submit_review_request(state, final_request(first_id), "commit-round-1")
        self.assertEqual(state["WORKFLOW_STATE"], "FINAL_REVIEW_PENDING")
        self.assertFalse(evaluate_completion_gate(state).work_item_completed)

        revised = apply_transport_review(
            state,
            transport_state(
                first_id,
                rr_review(
                    first_id,
                    "REVISE",
                    ac2_status="NOT_MET",
                    next_work_order="Add the missing AC2 regression and rerun tests.",
                ),
            ),
            "commit-round-1",
        )
        self.assertTrue(revised.authoritative)
        self.assertEqual(revised.outcome, "REVISION_REQUIRED")
        self.assertEqual(state["WORKFLOW_STATE"], "REVISION_REQUIRED")
        self.assertEqual(evaluate_completion_gate(state).outcome, CONTINUE_BOUNDED)
        self.assertIn("missing AC2 regression", state["CURRENT_REQUIRED_ACTION"]["DESCRIPTION"])

        record_revision_applied(state, "commit-round-2 includes AC2 regression")
        self.assertEqual(state["WORKFLOW_STATE"], "EXECUTING")
        second_id = f"{WORK_ITEM_ID}-E2E-R2-FINAL"
        submit_review_request(state, final_request(second_id), "commit-round-2")
        self.assertEqual(state["WORKFLOW_STATE"], "FINAL_REVIEW_PENDING")
        self.assertIsNone(state["CURRENT_REQUIRED_ACTION"])

        approved = apply_transport_review(
            state,
            transport_state(second_id, rr_review(second_id, "APPROVE")),
            "commit-round-2",
        )
        self.assertTrue(approved.authoritative)
        self.assertEqual(approved.outcome, "COMPLETED")
        gate = evaluate_completion_gate(state)
        self.assertEqual(gate.outcome, ALLOW_STOP)
        self.assertTrue(gate.work_item_completed)

    def test_transport_achieved_label_cannot_complete_a_revision(self):
        state = loop_state()
        request_id = f"{WORK_ITEM_ID}-R1-FINAL"
        submit_review_request(state, final_request(request_id), "artifact-1")
        result = apply_transport_review(
            state,
            transport_state(
                request_id,
                rr_review(request_id, "REVISE", ac2_status="NOT_MET", next_work_order="Fix AC2"),
            ),
            "artifact-1",
        )
        self.assertTrue(result.authoritative)
        self.assertEqual(state["WORKFLOW_STATE"], "REVISION_REQUIRED")
        self.assertFalse(evaluate_completion_gate(state).work_item_completed)

    def test_mismatched_binding_is_non_authoritative_and_keeps_pending_state(self):
        for field, value in (
            ("PROTOCOL_VERSION", "ACF-9.9"),
            ("WORK_ITEM_ID", "WRONG"),
            ("IN_REPLY_TO_REVIEW_REQUEST_ID", "OLD"),
            ("REVIEW_KIND", "INTERMEDIATE"),
        ):
            with self.subTest(field=field):
                state = loop_state()
                request_id = f"{WORK_ITEM_ID}-{field}-FINAL"
                submit_review_request(state, final_request(request_id), "artifact-1")
                before = copy.deepcopy(state)
                decision = {
                    "PROTOCOL_VERSION": "ACF-0.1",
                    "WORK_ITEM_ID": WORK_ITEM_ID,
                    "IN_REPLY_TO_REVIEW_REQUEST_ID": request_id,
                    "REVIEW_KIND": "FINAL",
                    "REVIEW_DECISION": "APPROVE",
                    "ACCEPTANCE_STATUS": [
                        {"CRITERION": "AC1", "STATUS": "MET"},
                        {"CRITERION": "AC2", "STATUS": "MET"},
                    ],
                    "REQUIRED_ACTIONS": [],
                    "USER_DECISION_REQUIRED": "NONE",
                    "REVIEWED_STATE_CURRENT": True,
                }
                decision[field] = value
                result = apply_review_decision(state, decision)
                self.assertFalse(result.authoritative)
                self.assertEqual(state, before)

    def test_stale_artifact_approval_is_non_authoritative(self):
        state = loop_state()
        request_id = f"{WORK_ITEM_ID}-STALE-FINAL"
        submit_review_request(state, final_request(request_id), "reviewed-commit")
        result = apply_transport_review(
            state,
            transport_state(request_id, rr_review(request_id, "APPROVE")),
            "changed-after-request",
        )
        self.assertFalse(result.authoritative)
        self.assertEqual(state["WORKFLOW_STATE"], "FINAL_REVIEW_PENDING")
        self.assertIsNone(state["AUTHORITATIVE_REVIEW_DECISION"])

    def test_incomplete_or_duplicate_acceptance_coverage_is_rejected(self):
        for statuses in (
            [{"CRITERION": "AC1", "STATUS": "MET"}],
            [
                {"CRITERION": "AC1", "STATUS": "MET"},
                {"CRITERION": "AC1", "STATUS": "MET"},
            ],
            [
                {"CRITERION": "AC1", "STATUS": "MET"},
                {"CRITERION": "AC2", "STATUS": "PASS"},
            ],
        ):
            with self.subTest(statuses=statuses):
                state = loop_state()
                request_id = f"{WORK_ITEM_ID}-COVERAGE-{len(statuses)}-FINAL"
                submit_review_request(state, final_request(request_id), "artifact-1")
                decision = {
                    "PROTOCOL_VERSION": "ACF-0.1",
                    "WORK_ITEM_ID": WORK_ITEM_ID,
                    "IN_REPLY_TO_REVIEW_REQUEST_ID": request_id,
                    "REVIEW_KIND": "FINAL",
                    "REVIEW_DECISION": "APPROVE",
                    "ACCEPTANCE_STATUS": statuses,
                    "REQUIRED_ACTIONS": [],
                    "USER_DECISION_REQUIRED": "NONE",
                    "REVIEWED_STATE_CURRENT": True,
                }
                self.assertFalse(apply_review_decision(state, decision).authoritative)
                self.assertEqual(state["WORKFLOW_STATE"], "FINAL_REVIEW_PENDING")

    def test_revision_requires_new_request_id_and_same_kind(self):
        state = loop_state()
        request_id = f"{WORK_ITEM_ID}-R1-FINAL"
        submit_review_request(state, final_request(request_id), "artifact-1")
        apply_transport_review(
            state,
            transport_state(
                request_id,
                rr_review(request_id, "REVISE", ac2_status="NOT_MET", next_work_order="Fix AC2"),
            ),
            "artifact-1",
        )
        record_revision_applied(state, "AC2 fixed")
        with self.assertRaisesRegex(ValueError, "unique"):
            submit_review_request(state, final_request(request_id), "artifact-2")
        intermediate = final_request(f"{WORK_ITEM_ID}-R2-INTERMEDIATE")
        intermediate["REVIEW_KIND"] = "INTERMEDIATE"
        intermediate["REVIEW_TRIGGER"] = "BLOCKER"
        intermediate["EXECUTION_ASSESSMENT"]["CLAIMED_STATUS"] = "IN_PROGRESS"
        with self.assertRaisesRegex(ValueError, "preserve Review Kind"):
            submit_review_request(state, intermediate, "artifact-2")

    def test_wire_binding_block_is_required_and_must_match_message_id(self):
        state = loop_state()
        request_id = f"{WORK_ITEM_ID}-WIRE-FINAL"
        submit_review_request(state, final_request(request_id), "artifact-1")
        malformed = rr_review(request_id, "APPROVE", validation="NONE")
        result = apply_transport_review(
            state, transport_state(request_id, malformed), "artifact-1"
        )
        self.assertFalse(result.authoritative)
        self.assertEqual(state["WORKFLOW_STATE"], "FINAL_REVIEW_PENDING")

    def test_wire_approve_with_blockers_is_non_authoritative(self):
        state = loop_state()
        request_id = f"{WORK_ITEM_ID}-BLOCKED-FINAL"
        submit_review_request(state, final_request(request_id), "artifact-1")
        review = rr_review(request_id, "APPROVE")
        review["BLOCKERS"] = "AC2 evidence is unavailable"
        result = apply_transport_review(
            state, transport_state(request_id, review), "artifact-1"
        )
        self.assertFalse(result.authoritative)
        self.assertEqual(state["WORKFLOW_STATE"], "FINAL_REVIEW_PENDING")

    def test_review_request_cannot_weaken_agreed_criterion_content(self):
        state = loop_state()
        request = final_request(f"{WORK_ITEM_ID}-WEAKENED-FINAL")
        request["ACCEPTANCE_CRITERIA"][0]["DESCRIPTION"] = "weaker requirement"
        with self.assertRaisesRegex(ValueError, "exactly snapshot"):
            submit_review_request(state, request, "artifact-1")
        self.assertEqual(state["WORKFLOW_STATE"], "EXECUTING")

    def test_review_request_rejects_empty_required_evidence(self):
        state = loop_state()
        request = final_request(f"{WORK_ITEM_ID}-EMPTY-FINAL")
        request["EVIDENCE"] = ""
        with self.assertRaisesRegex(ValueError, "EVIDENCE"):
            submit_review_request(state, request, "artifact-1")
        request = final_request(f"{WORK_ITEM_ID}-NULL-ASSESSMENT-FINAL")
        request["EXECUTION_ASSESSMENT"]["UNVERIFIED"] = None
        with self.assertRaisesRegex(ValueError, "Assessment"):
            submit_review_request(state, request, "artifact-1")

    def test_pending_stale_snapshot_returns_to_executing_for_new_same_kind_request(self):
        state = loop_state()
        first_id = f"{WORK_ITEM_ID}-STALE-R1-FINAL"
        submit_review_request(state, final_request(first_id), "artifact-1")
        mark_reviewed_state_stale(state, "material artifact change")
        self.assertEqual(state["WORKFLOW_STATE"], "EXECUTING")
        self.assertIsNone(state["PENDING_REVIEW_REQUEST"])
        second_id = f"{WORK_ITEM_ID}-STALE-R2-FINAL"
        submit_review_request(state, final_request(second_id), "artifact-2")
        self.assertEqual(state["WORKFLOW_STATE"], "FINAL_REVIEW_PENDING")

    def test_acceptance_status_without_evidence_is_non_authoritative(self):
        state = loop_state()
        request_id = f"{WORK_ITEM_ID}-NO-EVIDENCE-FINAL"
        submit_review_request(state, final_request(request_id), "artifact-1")
        decision = {
            "PROTOCOL_VERSION": "ACF-0.1",
            "WORK_ITEM_ID": WORK_ITEM_ID,
            "IN_REPLY_TO_REVIEW_REQUEST_ID": request_id,
            "REVIEW_KIND": "FINAL",
            "REVIEW_DECISION": "APPROVE",
            "ACCEPTANCE_STATUS": [
                {"CRITERION": "AC1", "STATUS": "MET"},
                {"CRITERION": "AC2", "STATUS": "MET"},
            ],
            "REQUIRED_ACTIONS": [],
            "USER_DECISION_REQUIRED": "NONE",
            "REVIEWED_STATE_CURRENT": True,
        }
        self.assertFalse(apply_review_decision(state, decision).authoritative)
        self.assertEqual(state["WORKFLOW_STATE"], "FINAL_REVIEW_PENDING")

    def test_wire_met_status_with_none_evidence_is_non_authoritative(self):
        state = loop_state()
        request_id = f"{WORK_ITEM_ID}-NONE-EVIDENCE-FINAL"
        submit_review_request(state, final_request(request_id), "artifact-1")
        review = rr_review(request_id, "APPROVE")
        review["ACCEPTANCE_STATUS"] = review["ACCEPTANCE_STATUS"].replace(
            "EVIDENCE: artifact diff", "EVIDENCE: NONE"
        )
        result = apply_transport_review(
            state, transport_state(request_id, review), "artifact-1"
        )
        self.assertFalse(result.authoritative)
        self.assertEqual(state["WORKFLOW_STATE"], "FINAL_REVIEW_PENDING")

    def test_cli_persists_identity_verified_revision_state(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary_directory:
            directory = Path(temporary_directory)
            contract_path = directory / "contract.json"
            state_path = directory / "state.json"
            request_path = directory / "request.json"
            transport_path = directory / "transport.json"
            request_id = f"{WORK_ITEM_ID}-CLI-R1-FINAL"
            contract_path.write_text(json.dumps({
                "WORK_ITEM_ID": WORK_ITEM_ID,
                "GOAL": "exercise one real two-round review",
                "ACCEPTANCE_CRITERIA": ACCEPTANCE_CRITERIA,
            }), encoding="utf-8")
            request_path.write_text(json.dumps(final_request(request_id)), encoding="utf-8")
            transport_path.write_text(json.dumps(transport_state(
                request_id,
                rr_review(
                    request_id,
                    "REVISE",
                    ac2_status="NOT_MET",
                    next_work_order="Add the missing AC2 regression.",
                ),
            )), encoding="utf-8")
            driver = str(ROOT / "scripts" / "acf_review_loop.py")
            for arguments in (
                ["initialize", "--contract", str(contract_path), "--state", str(state_path)],
                [
                    "submit-review", "--state", str(state_path), "--request", str(request_path),
                    "--artifact-id", "commit-round-1",
                ],
                [
                    "ingest-review", "--state", str(state_path),
                    "--transport-state", str(transport_path),
                    "--current-artifact-id", "commit-round-1",
                ],
            ):
                completed = subprocess.run(
                    [sys.executable, driver, *arguments], text=True, capture_output=True, check=False
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)
            persisted = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(persisted["WORKFLOW_STATE"], "REVISION_REQUIRED")
            self.assertIn("missing AC2 regression", persisted["CURRENT_REQUIRED_ACTION"]["DESCRIPTION"])


if __name__ == "__main__":
    unittest.main()
