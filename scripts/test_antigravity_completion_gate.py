import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


completion_gate = _load("runtime.completion_gate", ROOT / "runtime" / "completion_gate.py")
stop_hook = _load("stop_hook", ROOT / "adapters" / "antigravity" / "stop_hook.py")


def base_state(workflow_state="EXECUTING"):
    return {
        "PROTOCOL_VERSION": "ACF-0.1",
        "WORK_ITEM_ID": "WORK-001",
        "WORKFLOW_STATE": workflow_state,
        "UNRESOLVED_USER_DECISION": False,
        "PENDING_REVIEW_REQUEST": {
            "REVIEW_REQUEST_ID": "WORK-001-R1-FINAL",
            "REVIEW_KIND": "FINAL",
            "ACCEPTANCE_CRITERIA": [{"CRITERION": "AC1"}],
        },
        "AUTHORITATIVE_REVIEW_DECISION": {
            "PROTOCOL_VERSION": "ACF-0.1",
            "WORK_ITEM_ID": "WORK-001",
            "IN_REPLY_TO_REVIEW_REQUEST_ID": "WORK-001-R1-FINAL",
            "REVIEW_KIND": "FINAL",
            "REVIEW_DECISION": "APPROVE",
            "ACCEPTANCE_STATUS": [{"CRITERION": "AC1", "STATUS": "MET"}],
            "USER_DECISION_REQUIRED": "NONE",
            "REVIEWED_STATE_CURRENT": True,
        },
        "CURRENT_REQUIRED_ACTION": {
            "ACTION_ID": "ACTION-1",
            "DESCRIPTION": "finish required validation",
            "STATUS": "PENDING",
        },
        "CONTINUATION_STATE": {
            "ACTION_ID": "ACTION-1",
            "CONTINUATION_COUNT": 0,
            "CONTINUATION_BUDGET": 1,
            "CONTINUE_REASON": "NONE",
        },
    }


class PolicyTests(unittest.TestCase):
    def test_completed_requires_derived_authoritative_approval(self):
        state = base_state("COMPLETED")
        result = completion_gate.evaluate_completion_gate(state)
        self.assertEqual(result.outcome, completion_gate.ALLOW_STOP)
        self.assertTrue(result.work_item_completed)
        state["AUTHORITATIVE_REVIEW_DECISION"]["REVIEWED_STATE_CURRENT"] = False
        result = completion_gate.evaluate_completion_gate(state)
        self.assertEqual(result.outcome, completion_gate.BLOCK_AND_ESCALATE)
        self.assertFalse(result.work_item_completed)

    def test_pending_review_and_user_wait_allow_idle_without_completion(self):
        for workflow_state in (
            "INTERMEDIATE_REVIEW_PENDING", "FINAL_REVIEW_PENDING", "WAITING_FOR_USER"
        ):
            with self.subTest(workflow_state=workflow_state):
                result = completion_gate.evaluate_completion_gate(base_state(workflow_state))
                self.assertEqual(result.outcome, completion_gate.ALLOW_STOP)
                self.assertFalse(result.work_item_completed)

    def test_revision_continuation_is_bounded(self):
        state = base_state("REVISION_REQUIRED")
        first = completion_gate.evaluate_completion_gate(state)
        self.assertEqual(first.outcome, completion_gate.CONTINUE_BOUNDED)
        completion_gate.consume_continuation(state, first.reason)
        second = completion_gate.evaluate_completion_gate(state)
        self.assertEqual(second.outcome, completion_gate.BLOCK_AND_ESCALATE)

    def test_stale_or_mismatched_approval_cannot_complete(self):
        for field, value in (
            ("IN_REPLY_TO_REVIEW_REQUEST_ID", "OLD-REQUEST"),
            ("REVIEW_KIND", "INTERMEDIATE"),
            ("PROTOCOL_VERSION", "ACF-9.9"),
        ):
            with self.subTest(field=field):
                state = base_state("COMPLETED")
                state["AUTHORITATIVE_REVIEW_DECISION"][field] = value
                self.assertFalse(completion_gate.final_approval_is_authoritative(state))

    def test_missing_agreed_criterion_is_not_authoritative(self):
        state = base_state("COMPLETED")
        state["PENDING_REVIEW_REQUEST"]["ACCEPTANCE_CRITERIA"] = [
            {"CRITERION": "AC1"}, {"CRITERION": "AC2"}
        ]
        self.assertFalse(completion_gate.final_approval_is_authoritative(state))

    def test_complete_agreed_criterion_coverage_is_authoritative(self):
        state = base_state("COMPLETED")
        state["PENDING_REVIEW_REQUEST"]["ACCEPTANCE_CRITERIA"] = [
            {"CRITERION": "AC1"}, {"CRITERION": "AC2"}
        ]
        state["AUTHORITATIVE_REVIEW_DECISION"]["ACCEPTANCE_STATUS"] = [
            {"CRITERION": "AC1", "STATUS": "MET"},
            {"CRITERION": "AC2", "STATUS": "MET"},
        ]
        self.assertTrue(completion_gate.final_approval_is_authoritative(state))

    def test_duplicate_or_malformed_criterion_identity_is_not_authoritative(self):
        invalid_pairs = (
            (
                [{"CRITERION": "AC1"}, {"CRITERION": "AC1"}],
                [{"CRITERION": "AC1", "STATUS": "MET"}],
            ),
            (
                [{"CRITERION": "AC1"}],
                [
                    {"CRITERION": "AC1", "STATUS": "MET"},
                    {"CRITERION": "AC1", "STATUS": "MET"},
                ],
            ),
            (
                [{"CRITERION": "AC1"}],
                [{"CRITERION": "", "STATUS": "MET"}],
            ),
        )
        for agreed, statuses in invalid_pairs:
            with self.subTest(agreed=agreed, statuses=statuses):
                state = base_state("COMPLETED")
                state["PENDING_REVIEW_REQUEST"]["ACCEPTANCE_CRITERIA"] = agreed
                state["AUTHORITATIVE_REVIEW_DECISION"]["ACCEPTANCE_STATUS"] = statuses
                self.assertFalse(completion_gate.final_approval_is_authoritative(state))


class HookTranslationTests(unittest.TestCase):
    def test_exact_route_continues_once_and_unrelated_context_is_ignored(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary_directory:
            root = Path(temporary_directory)
            workspace = root / "workspace"
            workspace.mkdir()
            state_path = root / "state.json"
            config_path = root / "config.json"
            evidence_path = root / "evidence.jsonl"
            state_path.write_text(json.dumps(base_state("REVISION_REQUIRED")), encoding="utf-8")
            config_path.write_text(json.dumps({
                "adapter_version": "AG-CG-0.1",
                "routes": [{
                    "route_id": "route-1",
                    "workspace_path": str(workspace),
                    "conversation_id": "conversation-1",
                    "work_item_id": "WORK-001",
                    "state_path": str(state_path),
                    "evidence_path": str(evidence_path),
                }],
            }), encoding="utf-8")
            payload = {
                "conversationId": "conversation-1",
                "workspacePaths": [str(workspace)],
                "executionNum": 0,
                "terminationReason": "NO_TOOL_CALL",
                "fullyIdle": True,
            }

            first = stop_hook.handle_stop(config_path, payload)
            second = stop_hook.handle_stop(config_path, payload)
            unrelated = stop_hook.handle_stop(config_path, {**payload, "conversationId": "other"})

            self.assertEqual(first["decision"], "continue")
            self.assertEqual(second["decision"], "stop")
            self.assertEqual(unrelated["decision"], "ignore")
            persisted = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(persisted["CONTINUATION_STATE"]["CONTINUATION_COUNT"], 1)
            self.assertEqual(len(evidence_path.read_text(encoding="utf-8").splitlines()), 2)

    def test_matching_route_with_wrong_work_item_blocks(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary_directory:
            root = Path(temporary_directory)
            workspace = root / "workspace"
            workspace.mkdir()
            state_path = root / "state.json"
            config_path = root / "config.json"
            state_path.write_text(json.dumps(base_state()), encoding="utf-8")
            config_path.write_text(json.dumps({
                "adapter_version": "AG-CG-0.1",
                "routes": [{
                    "route_id": "route-1",
                    "workspace_path": str(workspace),
                    "work_item_id": "ANOTHER-WORK-ITEM",
                    "state_path": str(state_path),
                }],
            }), encoding="utf-8")
            result = stop_hook.handle_stop(config_path, {
                "conversationId": "conversation-1",
                "workspacePaths": [str(workspace)],
            })
            self.assertEqual(result["decision"], "stop")
            self.assertIn("Work Item mismatch", result["reason"])

    def test_cli_translates_waiting_for_user_to_stop_without_completion(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary_directory:
            root = Path(temporary_directory)
            workspace = root / "workspace"
            workspace.mkdir()
            state_path = root / "state.json"
            config_path = root / "config.json"
            state_path.write_text(json.dumps(base_state("WAITING_FOR_USER")), encoding="utf-8")
            config_path.write_text(json.dumps({
                "adapter_version": "AG-CG-0.1",
                "routes": [{
                    "route_id": "route-1",
                    "workspace_path": str(workspace),
                    "work_item_id": "WORK-001",
                    "state_path": str(state_path),
                }],
            }), encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(ROOT / "adapters" / "antigravity" / "stop_hook.py"),
                 "--config", str(config_path)],
                input=json.dumps({"conversationId": "conversation-1", "workspacePaths": [str(workspace)]}),
                text=True,
                capture_output=True,
                check=False,
            )
            response = json.loads(completed.stdout)
            self.assertEqual(completed.returncode, 0)
            self.assertEqual(response["decision"], "stop")
            self.assertIn("WAITING_FOR_USER", response["reason"])


if __name__ == "__main__":
    unittest.main()
