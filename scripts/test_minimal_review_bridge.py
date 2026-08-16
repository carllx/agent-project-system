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

    def test_a_b_c_d_canonical_rendered_request_structure(self) -> None:
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

    def test_e_request_hash_hashes_exact_rendered_message(self) -> None:
        rendered = render_canonical_review_request(self.req_id, self.art_id, self.task)
        h = compute_request_hash(rendered)
        expected = hashlib.sha256(rendered.encode("utf-8")).hexdigest()
        self.assertEqual(h, expected)

    def test_f_deterministic_rendering(self) -> None:
        r1 = render_canonical_review_request(self.req_id, self.art_id, self.task)
        r2 = render_canonical_review_request(f"  {self.req_id}  ", f"{self.art_id}\n", f"\n{self.task}\n")
        self.assertEqual(r1, r2)
        self.assertEqual(compute_request_hash(r1), compute_request_hash(r2))

    def test_g_changed_inputs_change_canonical_hash(self) -> None:
        base = compute_request_hash(render_canonical_review_request(self.req_id, self.art_id, self.task))

        h_req = compute_request_hash(render_canonical_review_request("REQ-DIFF", self.art_id, self.task))
        self.assertNotEqual(base, h_req)

        h_art = compute_request_hash(render_canonical_review_request(self.req_id, "sha256-diff", self.task))
        self.assertNotEqual(base, h_art)

        h_task = compute_request_hash(render_canonical_review_request(self.req_id, self.art_id, "Different task"))
        self.assertNotEqual(base, h_task)

    def test_h_caller_cannot_override_schema_through_separate_parameter(self) -> None:
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
                review_prompt="Do this verification.",
                receipt_dir=temp_dir,
                conversation_id="conv-test",
                opencli_runner=runner,
            )
            self.assertEqual(res["status"], "RESPONSE_PENDING")
            self.assertEqual(len(dispatched_prompts), 1)
            self.assertIn("BROWSER_REVIEW_REQUEST", dispatched_prompts[0])
            self.assertIn("REQUIRED_RESPONSE_FORMAT:", dispatched_prompts[0])
            self.assertIn("REQUEST_ID: REQ-CANONICAL-001", dispatched_prompts[0])
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_i_bootstrap_uses_fixed_inert_payload(self) -> None:
        dispatched_prompts: list[str] = []

        def runner(args: list[str], timeout: int) -> tuple[int, str, str]:
            dispatched_prompts.append(args[-1])
            stdout = json.dumps([{
                "conversationId": "conv-fixed-boot",
                "response": "Ready.",
            }])
            return 0, stdout, ""

        res = bootstrap_conversation(opencli_runner=runner)
        self.assertEqual(res["status"], "CONVERSATION_ESTABLISHED")
        self.assertEqual(len(dispatched_prompts), 1)
        self.assertEqual(dispatched_prompts[0], INERT_BOOTSTRAP_PROMPT)


class TestFastReturnTransportSemantics(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="aps-fast-return-test-"))
        self.receipt_dir = self.temp_dir / "receipts"
        self.req_id = "REQ-FAST-001"
        self.art_id = "sha256-art-fast-001"
        self.prompt = "Please verify fast submission."
        self.known_conv = "conv-fast-12345"

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_a_formal_submit_includes_wait_false(self) -> None:
        dispatched_args: list[list[str]] = []

        def runner(args: list[str], timeout: int) -> tuple[int, str, str]:
            dispatched_args.append(args)
            stdout = json.dumps([{
                "conversationId": self.known_conv,
                "response": "",
            }])
            return 0, stdout, ""

        dispatch_review(
            request_id=self.req_id,
            artifact_id=self.art_id,
            review_prompt=self.prompt,
            receipt_dir=self.receipt_dir,
            conversation_id=self.known_conv,
            opencli_runner=runner,
        )

        self.assertEqual(len(dispatched_args), 1)
        cmd = dispatched_args[0]
        self.assertIn("--wait", cmd)
        idx = cmd.index("--wait")
        self.assertEqual(cmd[idx + 1], "false")

    def test_b_c_formal_submit_does_not_wait_for_browser_and_returns_response_pending(self) -> None:
        def runner(args: list[str], timeout: int) -> tuple[int, str, str]:
            # Mock opencli ask --wait false immediate return (empty response field)
            stdout = json.dumps([{
                "conversationId": self.known_conv,
                "response": "",
            }])
            return 0, stdout, ""

        res = dispatch_review(
            request_id=self.req_id,
            artifact_id=self.art_id,
            review_prompt=self.prompt,
            receipt_dir=self.receipt_dir,
            conversation_id=self.known_conv,
            opencli_runner=runner,
        )

        self.assertEqual(res["status"], "RESPONSE_PENDING")
        self.assertEqual(res["request_id"], self.req_id)
        self.assertEqual(res["conversation_id"], self.known_conv)
        self.assertTrue(res["write_attempted"])

    def test_d_send_attempted_remains_durable_after_submit(self) -> None:
        def runner(args: list[str], timeout: int) -> tuple[int, str, str]:
            return 0, json.dumps([{"conversationId": self.known_conv}]), ""

        dispatch_review(
            request_id=self.req_id,
            artifact_id=self.art_id,
            review_prompt=self.prompt,
            receipt_dir=self.receipt_dir,
            conversation_id=self.known_conv,
            opencli_runner=runner,
        )

        rcp = load_receipt(self.receipt_dir, self.req_id)
        self.assertIsNotNone(rcp)
        assert rcp is not None
        self.assertEqual(rcp.send_state, STATE_SEND_ATTEMPTED)
        self.assertEqual(rcp.conversation_id, self.known_conv)
        self.assertIsNotNone(rcp.send_attempted_at)
        self.assertIsNone(rcp.response_received_at)

    def test_e_duplicate_invocation_cannot_send_again(self) -> None:
        call_count = 0
        detail_count = 0

        def runner(args: list[str], timeout: int) -> tuple[int, str, str]:
            nonlocal call_count, detail_count
            if "ask" in args:
                call_count += 1
            if "detail" in args:
                detail_count += 1
            return 0, json.dumps([{"conversationId": self.known_conv}]), ""

        # First call: sends write
        res1 = dispatch_review(
            request_id=self.req_id,
            artifact_id=self.art_id,
            review_prompt=self.prompt,
            receipt_dir=self.receipt_dir,
            conversation_id=self.known_conv,
            opencli_runner=runner,
        )
        self.assertEqual(res1["status"], "RESPONSE_PENDING")
        self.assertEqual(call_count, 1)
        self.assertEqual(detail_count, 0)

        # Second call: performs read-only detail check, does NOT call ask
        res2 = dispatch_review(
            request_id=self.req_id,
            artifact_id=self.art_id,
            review_prompt=self.prompt,
            receipt_dir=self.receipt_dir,
            conversation_id=self.known_conv,
            opencli_runner=runner,
        )
        self.assertEqual(res2["status"], "RESPONSE_PENDING")
        self.assertEqual(call_count, 1)  # Zero additional ask calls!
        self.assertEqual(detail_count, 1)  # Read-only reconciliation triggered

    def test_f_reconcile_is_strictly_read_only(self) -> None:
        executed_commands: list[list[str]] = []

        def runner(args: list[str], timeout: int) -> tuple[int, str, str]:
            executed_commands.append(args)
            return 0, "[]", ""

        rcp = ReviewReceipt(
            request_id=self.req_id,
            request_hash="hash-123",
            artifact_id=self.art_id,
            conversation_id=self.known_conv,
            send_state=STATE_SEND_ATTEMPTED,
            created_at="2026-08-16T08:00:00Z",
        )
        save_receipt_atomic(self.receipt_dir, rcp)

        reconcile_review(
            request_id=self.req_id,
            artifact_id=self.art_id,
            receipt_dir=self.receipt_dir,
            conversation_id=self.known_conv,
            opencli_runner=runner,
        )

        self.assertEqual(len(executed_commands), 1)
        self.assertIn("detail", executed_commands[0])
        self.assertNotIn("ask", executed_commands[0])

    def test_g_reconcile_without_response_returns_response_pending(self) -> None:
        def runner(args: list[str], timeout: int) -> tuple[int, str, str]:
            # Detail returns only the user's message, no assistant response yet
            messages = [{"Role": "user", "Text": "Please review"}]
            return 0, json.dumps(messages), ""

        rcp = ReviewReceipt(
            request_id=self.req_id,
            request_hash="hash-123",
            artifact_id=self.art_id,
            conversation_id=self.known_conv,
            send_state=STATE_SEND_ATTEMPTED,
            created_at="2026-08-16T08:00:00Z",
        )
        save_receipt_atomic(self.receipt_dir, rcp)

        res = reconcile_review(
            request_id=self.req_id,
            artifact_id=self.art_id,
            receipt_dir=self.receipt_dir,
            conversation_id=self.known_conv,
            opencli_runner=runner,
        )

        self.assertEqual(res["status"], "RESPONSE_PENDING")
        rcp_after = load_receipt(self.receipt_dir, self.req_id)
        assert rcp_after is not None
        self.assertEqual(rcp_after.send_state, STATE_SEND_ATTEMPTED)

    def test_h_reconcile_with_matching_response_reaches_response_received(self) -> None:
        resp_payload = {
            "request_id": self.req_id,
            "artifact_id": self.art_id,
            "decision": "APPROVE",
            "feedback": "All good",
            "next_steps": [],
        }

        def runner(args: list[str], timeout: int) -> tuple[int, str, str]:
            messages = [
                {"Role": "user", "Text": "Please review"},
                {"Role": "assistant", "Text": f"```json\n{json.dumps(resp_payload)}\n```"},
            ]
            return 0, json.dumps(messages), ""

        rcp = ReviewReceipt(
            request_id=self.req_id,
            request_hash="hash-123",
            artifact_id=self.art_id,
            conversation_id=self.known_conv,
            send_state=STATE_SEND_ATTEMPTED,
            created_at="2026-08-16T08:00:00Z",
        )
        save_receipt_atomic(self.receipt_dir, rcp)

        res = reconcile_review(
            request_id=self.req_id,
            artifact_id=self.art_id,
            receipt_dir=self.receipt_dir,
            conversation_id=self.known_conv,
            opencli_runner=runner,
        )

        self.assertEqual(res["status"], "RESPONSE_READY")
        self.assertEqual(res["response"]["decision"], "APPROVE")
        rcp_after = load_receipt(self.receipt_dir, self.req_id)
        assert rcp_after is not None
        self.assertEqual(rcp_after.send_state, STATE_RESPONSE_RECEIVED)
        self.assertIsNotNone(rcp_after.response_received_at)

    def test_i_bounded_default_timeout_is_not_120s(self) -> None:
        self.assertEqual(DEFAULT_COMMAND_TIMEOUT_SECONDS, 30)

    def test_j_no_internal_busy_poll_loop(self) -> None:
        call_count = 0

        def runner(args: list[str], timeout: int) -> tuple[int, str, str]:
            nonlocal call_count
            call_count += 1
            return 0, json.dumps([{"conversationId": self.known_conv}]), ""

        res = dispatch_review(
            request_id=self.req_id,
            artifact_id=self.art_id,
            review_prompt=self.prompt,
            receipt_dir=self.receipt_dir,
            conversation_id=self.known_conv,
            opencli_runner=runner,
        )

        # Must execute exactly once and return immediately without looping
        self.assertEqual(res["status"], "RESPONSE_PENDING")
        self.assertEqual(call_count, 1)


class TestMinimalResponseParsing(unittest.TestCase):
    def setUp(self) -> None:
        self.req_id = "REQ-TEST-001"
        self.art_id = "sha256-art-001"

    def test_valid_strict_response_fenced_json(self) -> None:
        raw = f"""Here is my review:
```json
{{
  "request_id": "{self.req_id}",
  "artifact_id": "{self.art_id}",
  "decision": "APPROVE",
  "feedback": "All changes verified successfully.",
  "next_steps": []
}}
```
"""
        parsed = parse_strict_response(raw, self.req_id, self.art_id)
        self.assertEqual(parsed["request_id"], self.req_id)
        self.assertEqual(parsed["artifact_id"], self.art_id)
        self.assertEqual(parsed["decision"], "APPROVE")
        self.assertEqual(parsed["feedback"], "All changes verified successfully.")
        self.assertEqual(parsed["next_steps"], [])

    def test_valid_strict_response_revise_and_blocked(self) -> None:
        raw_revise = json.dumps({
            "request_id": self.req_id,
            "artifact_id": self.art_id,
            "decision": "REVISE",
            "feedback": "Need fix in module X",
            "next_steps": ["Fix module X", "Add test"],
        })
        parsed_rev = parse_strict_response(raw_revise, self.req_id, self.art_id)
        self.assertEqual(parsed_rev["decision"], "REVISE")
        self.assertEqual(len(parsed_rev["next_steps"]), 2)

        raw_blocked = json.dumps({
            "request_id": self.req_id,
            "artifact_id": self.art_id,
            "decision": "BLOCKED",
            "feedback": "Security policy violation",
            "next_steps": [],
        })
        parsed_blk = parse_strict_response(raw_blocked, self.req_id, self.art_id)
        self.assertEqual(parsed_blk["decision"], "BLOCKED")

    def test_wrong_request_id_rejected(self) -> None:
        raw = json.dumps({
            "request_id": "REQ-WRONG",
            "artifact_id": self.art_id,
            "decision": "APPROVE",
            "feedback": "Looks good",
        })
        with self.assertRaises(ValueError) as ctx:
            parse_strict_response(raw, self.req_id, self.art_id)
        self.assertIn("request_id mismatch", str(ctx.exception))

    def test_wrong_artifact_id_rejected(self) -> None:
        raw = json.dumps({
            "request_id": self.req_id,
            "artifact_id": "sha256-wrong",
            "decision": "APPROVE",
            "feedback": "Looks good",
        })
        with self.assertRaises(ValueError) as ctx:
            parse_strict_response(raw, self.req_id, self.art_id)
        self.assertIn("artifact_id mismatch", str(ctx.exception))

    def test_invalid_decision_rejected(self) -> None:
        raw = json.dumps({
            "request_id": self.req_id,
            "artifact_id": self.art_id,
            "decision": "PASS_WITH_WARNINGS",
            "feedback": "Not valid enum",
        })
        with self.assertRaises(ValueError) as ctx:
            parse_strict_response(raw, self.req_id, self.art_id)
        self.assertIn("Invalid decision", str(ctx.exception))

    def test_malformed_response_rejected(self) -> None:
        with self.assertRaises(ValueError):
            parse_strict_response("This is not JSON at all", self.req_id, self.art_id)
        with self.assertRaises(ValueError):
            parse_strict_response("{ broken json", self.req_id, self.art_id)
        with self.assertRaises(ValueError):
            parse_strict_response("", self.req_id, self.art_id)


class TestCLIIntegration(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="aps-cli-env-"))
        self.receipt_dir = self.temp_dir / "receipts"
        self.req_id = "REQ-CLI-001"
        self.art_id = "sha256-art-cli"

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_cli_requires_conversation_for_review(self) -> None:
        import opencli_transport

        parser = opencli_transport.parser()
        with self.assertRaises(SystemExit):
            parser.parse_args([
                "review",
                "--request-id", self.req_id,
                "--artifact-id", self.art_id,
                "--prompt", "Test prompt",
            ])

    def test_cli_review_bootstrap_parser(self) -> None:
        import opencli_transport

        parser = opencli_transport.parser()
        args = parser.parse_args(["review-bootstrap", "--timeout", "30"])
        self.assertEqual(args.command, "review-bootstrap")
        self.assertEqual(args.timeout, 30)


if __name__ == "__main__":
    unittest.main()
