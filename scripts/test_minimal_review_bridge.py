"""Focused unit tests for the Minimal Browser Review Bridge Fast-Return Semantics."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL_SCRIPTS = ROOT / "skills" / "research-review-lead" / "scripts"
if str(SKILL_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SKILL_SCRIPTS))

from minimal_bridge import (
    DEFAULT_COMMAND_TIMEOUT_SECONDS,
    INERT_BOOTSTRAP_PROMPT,
    STATE_PREPARED,
    STATE_RESPONSE_RECEIVED,
    STATE_SEND_ATTEMPTED,
    ReviewReceipt,
    bootstrap_conversation,
    compute_request_hash,
    dispatch_review,
    load_receipt,
    parse_strict_response,
    reconcile_review,
    render_canonical_review_request,
    save_receipt_atomic,
)


class TestCanonicalEnvelopeAndHashing(unittest.TestCase):
    def setUp(self) -> None:
        self.req_id = "REQ-CANONICAL-001"
        self.art_id = "sha256-art-999"
        self.task = "Verify synthetic artifact correctness."

    def test_canonical_rendered_request_structure(self) -> None:
        rendered = render_canonical_review_request(self.req_id, self.art_id, self.task)

        # exact request_id
        self.assertIn(f"REQUEST_ID: {self.req_id}", rendered)
        self.assertIn(f'"request_id": "{self.req_id}"', rendered)

        # exact artifact_id
        self.assertIn(f"ARTIFACT_ID: {self.art_id}", rendered)
        self.assertIn(f'"artifact_id": "{self.art_id}"', rendered)

        # review_prompt exactly once
        self.assertEqual(rendered.count(self.task), 1)

        # strict response schema instructions
        self.assertIn("REQUIRED_RESPONSE_FORMAT:", rendered)
        self.assertIn("APPROVE | REVISE | BLOCKED", rendered)
        self.assertIn("RULES:", rendered)

    def test_request_hash_hashes_exact_rendered_message(self) -> None:
        rendered = render_canonical_review_request(self.req_id, self.art_id, self.task)
        h = compute_request_hash(rendered)
        expected = hashlib.sha256(rendered.encode("utf-8")).hexdigest()
        self.assertEqual(h, expected)

    def test_deterministic_rendering(self) -> None:
        r1 = render_canonical_review_request(self.req_id, self.art_id, self.task)
        r2 = render_canonical_review_request(f"  {self.req_id}  ", f"{self.art_id}\n", f"\n{self.task}\n")
        self.assertEqual(r1, r2)
        self.assertEqual(compute_request_hash(r1), compute_request_hash(r2))

    def test_changed_inputs_change_canonical_hash(self) -> None:
        base = compute_request_hash(render_canonical_review_request(self.req_id, self.art_id, self.task))

        h_req = compute_request_hash(render_canonical_review_request("REQ-DIFF", self.art_id, self.task))
        self.assertNotEqual(base, h_req)

        h_art = compute_request_hash(render_canonical_review_request(self.req_id, "sha256-diff", self.task))
        self.assertNotEqual(base, h_art)

        h_task = compute_request_hash(render_canonical_review_request(self.req_id, self.art_id, "Different task"))
        self.assertNotEqual(base, h_task)

    def test_caller_cannot_override_schema_through_separate_parameter(self) -> None:
        dispatched_prompts: list[str] = []

        def runner(args: list[str], timeout: int) -> tuple[int, str, str]:
            dispatched_prompts.append(args[-1])
            stdout = json.dumps([{
                "conversationId": "conv-test",
                "response": "",
            }])
            return 0, stdout, ""

        temp_dir = Path(tempfile.mkdtemp(prefix="aps-envelope-test-"))
        try:
            res = dispatch_review(
                request_id=self.req_id,
                artifact_id=self.art_id,
                review_prompt=self.task,
                receipt_dir=temp_dir,
                conversation_id="conv-test",
                opencli_runner=runner,
            )
            self.assertEqual(res["status"], "RESPONSE_PENDING")
            self.assertEqual(len(dispatched_prompts), 1)
            # Prompts must match the canonical envelope exactly
            self.assertEqual(dispatched_prompts[0], render_canonical_review_request(self.req_id, self.art_id, self.task))
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


class TestFirstConversationSafety(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="aps-bridge-first-conv-"))

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_bootstrap_uses_inert_prompt_and_creates_conversation(self) -> None:
        executed_cmds: list[list[str]] = []

        def runner(args: list[str], timeout: int) -> tuple[int, str, str]:
            executed_cmds.append(args)
            stdout = json.dumps([{
                "conversationId": "conv-uuid-12345",
                "conversationUrl": "https://chatgpt.com/c/conv-uuid-12345",
                "response": "Understood. Standing by for formal review requests.",
            }])
            return 0, stdout, ""

        res = bootstrap_conversation(opencli_runner=runner)
        self.assertEqual(res["status"], "CONVERSATION_ESTABLISHED")
        self.assertEqual(res["conversation_id"], "conv-uuid-12345")
        self.assertEqual(len(executed_cmds), 1)
        self.assertIn("--new", executed_cmds[0])
        self.assertIn(INERT_BOOTSTRAP_PROMPT, executed_cmds[0])

    def test_dispatch_review_requires_explicit_conversation_id(self) -> None:
        with self.assertRaisesRegex(ValueError, "conversation_id is required"):
            dispatch_review(
                request_id="REQ-001",
                artifact_id="art-001",
                review_prompt="prompt",
                receipt_dir=self.temp_dir,
                conversation_id="",
            )

    def test_whitespace_normalized_request_id_writes_once(self) -> None:
        calls: list[list[str]] = []

        def runner(args: list[str], timeout: int) -> tuple[int, str, str]:
            calls.append(args)
            return 0, json.dumps([{"conversationId": "conv-fixed", "response": ""}]), ""

        # First call with whitespace
        res1 = dispatch_review(
            request_id="  REQ-NORM-001  ",
            artifact_id="  art-norm-001  ",
            review_prompt="prompt",
            receipt_dir=self.temp_dir,
            conversation_id="  conv-fixed  ",
            opencli_runner=runner,
        )
        self.assertEqual(res1["status"], "RESPONSE_PENDING")
        self.assertEqual(len(calls), 1)

        # Second call with stripped ID - should NOT do external write (exact-once)
        res2 = dispatch_review(
            request_id="REQ-NORM-001",
            artifact_id="art-norm-001",
            review_prompt="prompt",
            receipt_dir=self.temp_dir,
            conversation_id="conv-fixed",
            opencli_runner=runner,
        )
        # Reconcile called instead of new write
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1][1], "detail")  # Detail reconcile, not ask


class TestExactConversationInvariants(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="aps-bridge-drift-"))

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_exact_conversation_drift_fails_closed_and_records_send_attempted(self) -> None:
        def runner(args: list[str], timeout: int) -> tuple[int, str, str]:
            # OpenCLI unexpectedly returns a different conversation ID
            return 0, json.dumps([{"conversationId": "foreign-conv-999", "response": ""}]), ""

        with self.assertRaisesRegex(RuntimeError, "Exact-target mismatch: OpenCLI returned foreign conversationId"):
            dispatch_review(
                request_id="REQ-DRIFT-001",
                artifact_id="art-drift-001",
                review_prompt="prompt",
                receipt_dir=self.temp_dir,
                conversation_id="target-conv-111",
                opencli_runner=runner,
            )

        # Verify receipt is in SEND_ATTEMPTED state with original target_conv (never rewritten)
        receipt = load_receipt(self.temp_dir, "REQ-DRIFT-001")
        self.assertIsNotNone(receipt)
        self.assertEqual(receipt.send_state, STATE_SEND_ATTEMPTED)
        self.assertEqual(receipt.conversation_id, "target-conv-111")
        self.assertIn("foreign-conv-999", receipt.last_error or "")

        # Subsequent dispatch should fail-closed / reconcile against target_conv, not resend
        def runner_detail(args: list[str], timeout: int) -> tuple[int, str, str]:
            return 0, json.dumps([]), ""

        res2 = dispatch_review(
            request_id="REQ-DRIFT-001",
            artifact_id="art-drift-001",
            review_prompt="prompt",
            receipt_dir=self.temp_dir,
            conversation_id="target-conv-111",
            opencli_runner=runner_detail,
        )
        self.assertEqual(res2["status"], "RESPONSE_PENDING")


class TestReconcileIdentity(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="aps-reconcile-test-"))
        # Seed receipt
        self.receipt = ReviewReceipt(
            request_id="REQ-REC-001",
            request_hash="hash-001",
            artifact_id="art-rec-001",
            conversation_id="conv-rec-123",
            send_state=STATE_SEND_ATTEMPTED,
            created_at="2026-08-16T12:00:00Z",
        )
        save_receipt_atomic(self.temp_dir, self.receipt)

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_reconcile_wrong_conversation_rejected_before_detail(self) -> None:
        detail_called = False

        def runner(args: list[str], timeout: int) -> tuple[int, str, str]:
            nonlocal detail_called
            detail_called = True
            return 0, "[]", ""

        with self.assertRaisesRegex(ValueError, "Reconcile conversation_id mismatch"):
            reconcile_review(
                request_id="REQ-REC-001",
                artifact_id="art-rec-001",
                receipt_dir=self.temp_dir,
                conversation_id="wrong-conv",
                opencli_runner=runner,
            )
        self.assertFalse(detail_called)

    def test_reconcile_wrong_artifact_rejected_before_detail(self) -> None:
        detail_called = False

        def runner(args: list[str], timeout: int) -> tuple[int, str, str]:
            nonlocal detail_called
            detail_called = True
            return 0, "[]", ""

        with self.assertRaisesRegex(ValueError, "Reconcile artifact_id mismatch"):
            reconcile_review(
                request_id="REQ-REC-001",
                artifact_id="wrong-art",
                receipt_dir=self.temp_dir,
                conversation_id="conv-rec-123",
                opencli_runner=runner,
            )
        self.assertFalse(detail_called)

    def test_reconcile_matching_receipt_uses_exact_stored_conversation(self) -> None:
        called_args: list[list[str]] = []

        def runner(args: list[str], timeout: int) -> tuple[int, str, str]:
            called_args.append(args)
            return 0, json.dumps([]), ""

        res = reconcile_review(
            request_id="REQ-REC-001",
            artifact_id="art-rec-001",
            receipt_dir=self.temp_dir,
            opencli_runner=runner,
        )
        self.assertEqual(res["status"], "RESPONSE_PENDING")
        self.assertEqual(len(called_args), 1)
        self.assertIn("conv-rec-123", called_args[0])

    def test_reconcile_matching_response_cannot_alter_conversation_binding(self) -> None:
        valid_response = (
            "```json\n"
            "{\n"
            '  "request_id": "REQ-REC-001",\n'
            '  "artifact_id": "art-rec-001",\n'
            '  "decision": "APPROVE",\n'
            '  "feedback": "LGTM",\n'
            '  "next_steps": []\n'
            "}\n"
            "```"
        )

        def runner(args: list[str], timeout: int) -> tuple[int, str, str]:
            return 0, json.dumps([{"role": "assistant", "text": valid_response}]), ""

        res = reconcile_review(
            request_id="REQ-REC-001",
            artifact_id="art-rec-001",
            receipt_dir=self.temp_dir,
            conversation_id="conv-rec-123",
            opencli_runner=runner,
        )
        self.assertEqual(res["status"], "RESPONSE_READY")
        self.assertEqual(res["response"]["decision"], "APPROVE")

        # Stored conversation is strictly preserved
        updated_receipt = load_receipt(self.temp_dir, "REQ-REC-001")
        self.assertEqual(updated_receipt.conversation_id, "conv-rec-123")
        self.assertEqual(updated_receipt.send_state, STATE_RESPONSE_RECEIVED)


class TestStrictResponseParser(unittest.TestCase):
    def setUp(self) -> None:
        self.req_id = "REQ-PARSE-001"
        self.art_id = "art-parse-001"

    def test_parse_valid_fenced_json(self) -> None:
        raw = (
            "Review comments here.\n"
            "```json\n"
            "{\n"
            f'  "request_id": "{self.req_id}",\n'
            f'  "artifact_id": "{self.art_id}",\n'
            '  "decision": "APPROVE",\n'
            '  "feedback": "Acceptance criteria met.",\n'
            '  "next_steps": []\n'
            "}\n"
            "```\n"
        )
        res = parse_strict_response(raw, self.req_id, self.art_id)
        self.assertEqual(res["decision"], "APPROVE")
        self.assertEqual(res["feedback"], "Acceptance criteria met.")
        self.assertEqual(res["next_steps"], [])

    def test_parse_valid_bare_json(self) -> None:
        raw = (
            "{\n"
            f'  "request_id": "{self.req_id}",\n'
            f'  "artifact_id": "{self.art_id}",\n'
            '  "decision": "REVISE",\n'
            '  "feedback": "Fix syntax.",\n'
            '  "next_steps": ["step 1"]\n'
            "}\n"
        )
        res = parse_strict_response(raw, self.req_id, self.art_id)
        self.assertEqual(res["decision"], "REVISE")
        self.assertEqual(res["next_steps"], ["step 1"])

    def test_parse_rejects_multiple_fenced_blocks(self) -> None:
        raw = (
            "```json\n"
            '{"request_id": "' + self.req_id + '", "artifact_id": "' + self.art_id + '", "decision": "APPROVE", "feedback": "ok", "next_steps": []}\n'
            "```\n"
            "```json\n"
            '{"request_id": "' + self.req_id + '", "artifact_id": "' + self.art_id + '", "decision": "REVISE", "feedback": "no", "next_steps": []}\n'
            "```"
        )
        with self.assertRaisesRegex(ValueError, "Ambiguous response: found 2 fenced JSON blocks"):
            parse_strict_response(raw, self.req_id, self.art_id)

    def test_parse_rejects_multiple_bare_json_objects(self) -> None:
        raw = (
            '{"request_id": "' + self.req_id + '", "artifact_id": "' + self.art_id + '", "decision": "APPROVE", "feedback": "ok", "next_steps": []}\n'
            '{"request_id": "' + self.req_id + '", "artifact_id": "' + self.art_id + '", "decision": "REVISE", "feedback": "no", "next_steps": []}'
        )
        with self.assertRaisesRegex(ValueError, "Ambiguous response: found 2 bare JSON objects"):
            parse_strict_response(raw, self.req_id, self.art_id)

    def test_parse_rejects_non_string_elements_in_next_steps(self) -> None:
        raw = (
            "```json\n"
            "{\n"
            f'  "request_id": "{self.req_id}",\n'
            f'  "artifact_id": "{self.art_id}",\n'
            '  "decision": "REVISE",\n'
            '  "feedback": "Fix items",\n'
            '  "next_steps": [123, {"key": "val"}]\n'
            "}\n"
            "```"
        )
        with self.assertRaisesRegex(ValueError, "next_steps\\[0\\] must be a string"):
            parse_strict_response(raw, self.req_id, self.art_id)

    def test_parse_rejects_empty_feedback(self) -> None:
        raw = (
            "```json\n"
            "{\n"
            f'  "request_id": "{self.req_id}",\n'
            f'  "artifact_id": "{self.art_id}",\n'
            '  "decision": "APPROVE",\n'
            '  "feedback": "   ",\n'
            '  "next_steps": []\n'
            "}\n"
            "```"
        )
        with self.assertRaisesRegex(ValueError, "feedback must be a non-empty string"):
            parse_strict_response(raw, self.req_id, self.art_id)


class TestFastReturnSubmitSemantics(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="aps-fast-submit-test-"))

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_formal_submit_uses_native_wait_false(self) -> None:
        dispatched_cmd: list[str] = []

        def runner(args: list[str], timeout: int) -> tuple[int, str, str]:
            dispatched_cmd.extend(args)
            stdout = json.dumps([{
                "conversationId": "conv-target-001",
                "response": "",
            }])
            return 0, stdout, ""

        res = dispatch_review(
            request_id="REQ-SUBMIT-001",
            artifact_id="art-submit-001",
            review_prompt="Prompt instructions",
            receipt_dir=self.temp_dir,
            conversation_id="conv-target-001",
            opencli_runner=runner,
        )

        self.assertEqual(res["status"], "RESPONSE_PENDING")
        self.assertEqual(res["request_id"], "REQ-SUBMIT-001")
        self.assertTrue(res["write_attempted"])

        # Check command args include --wait false
        self.assertIn("--wait", dispatched_cmd)
        wait_idx = dispatched_cmd.index("--wait")
        self.assertEqual(dispatched_cmd[wait_idx + 1], "false")

        # Check receipt was updated to SEND_ATTEMPTED
        receipt = load_receipt(self.temp_dir, "REQ-SUBMIT-001")
        self.assertIsNotNone(receipt)
        self.assertEqual(receipt.send_state, STATE_SEND_ATTEMPTED)


if __name__ == "__main__":
    unittest.main()
