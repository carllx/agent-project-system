"""Validate the self-contained Research Review Lead source skill package."""

from __future__ import annotations

import ast
import json
import re
import secrets
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "skills" / "research-review-lead"
ENTRY = PACKAGE / "SKILL.md"
VERSION = PACKAGE / "VERSION"
TRANSPORT_SCRIPT = PACKAGE / "scripts" / "opencli_transport.py"
TRANSPORT_TEST = ROOT / "scripts" / "test_opencli_transport.py"
REQUIRED_ASSETS = {
    "context-packet.md",
    "evidence-packet.md",
    "decision-request.md",
    "handoff.md",
    "rr-lead-init.md",
}
EXPECTED_PACKAGE_FILES = {
    "SKILL.md",
    "VERSION",
    "scripts/opencli_transport.py",
    *(f"assets/{name}" for name in REQUIRED_ASSETS),
}
REQUIRED_SKILL_MARKERS = {
    "Builder IDE Agent",
    "IDE-side Loop Driver",
    "Browser RR Lead",
    "OpenCLI",
    "PRECHECK",
    "PREPARE_MESSAGE",
    "CREATE_NEW_CONVERSATION",
    "VERIFY_NEW_CONVERSATION",
    "START_NEW_AND_SEND",
    "PRE_SEND_HISTORY_BASELINE",
    "VERIFY_NEW_URL_AND_EMPTY_READ",
    "PARSE_ASK_IDENTITY",
    "POST_SEND_STATUS",
    "BOUNDED_RECOVERY_IF_NEEDED",
    "SEND_MESSAGE",
    "CAPTURE_OR_RECOVER_CONVERSATION_ID",
    "POLL_OR_READ_RESPONSE",
    "PARSE_RR_REVIEW",
    "DELIVERY_STATE",
    "DELIVERY_UNKNOWN",
    "MISROUTED_DELIVERY",
    "RESPONSE_PENDING",
    "RESPONSE_READY",
    "RESPONSE_IDENTITY_VERIFIED",
    "RESPONSE_IDENTITY_AMBIGUOUS",
    "OUTBOUND_MESSAGE_IDENTITY_AMBIGUOUS",
    "RR_REVIEW_BEGIN",
    "RR_REVIEW_END",
    "MESSAGE_ID",
    "IN_REPLY_TO_MESSAGE_ID",
    "SHARED_OBJECTIVE",
    "ACCEPTANCE_CRITERIA",
    "EVIDENCE_REQUIRED",
    "COMMAND_WAIT_SECONDS",
    "MAX_RECOVERY_ATTEMPTS",
    "MAX_SEND_ATTEMPTS_PER_MESSAGE",
    "MAX_DETAIL_CHECKS",
    "MAX_EXTERNAL_COMMANDS",
    "MAX_EXPERIMENT_SECONDS",
    "prepare-new",
    "BLOCKED_BEFORE_EXECUTION",
    "HARD_FAILURE: TEST_PROTOCOL_VIOLATION",
    "REQUIRED_VALUE_UNRESOLVED",
    "UNRESOLVED_PLACEHOLDER_EXECUTION",
    "UNAUTHORIZED_IDLE_WAIT",
    "MAX_IDLE_WAIT_SECONDS=0",
    "MAX_SCHEDULE_CALLS=0",
    "MAX_POLL_ATTEMPTS=0",
    "MAX_BACKGROUND_RESULT_CHECKS=1",
    "MAX_BACKGROUND_WAIT_SECONDS=15",
    "FIXED_SCHEDULE_TIMER_ALLOWED=false",
    "SYNCHRONOUS_COMPLETION",
    "BACKGROUND_PROCESS_COMPLETION",
    "IDLE_TIMER_WAIT",
    "REPORT_VALIDATION_FAILED",
    "POST_SEND_HISTORY_REFRESH",
    "NEW_CANDIDATE_DIFF",
    "EXACT_ID_DETAIL_CHECK",
    "WRAPPER_SCHEDULE_CALL_COUNT",
    "AGENT_SCHEDULE_CALL_COUNT",
    "TOTAL_SCHEDULE_CALL_COUNT",
    "AGENT_TOOL_TRACE_VERIFICATION",
    "AGENT_BOUND_RESULT_RETRIEVAL_COUNT",
    "EXPERIMENT_ACCEPTANCE",
    "WHO_INITIATED_SCHEDULE",
    "PLACEHOLDER_VALIDATION_PERFORMED",
    "TERMINATED_IMMEDIATELY_AFTER_RESULT",
    "Conversation ID",
    "WORK_ITEM_ID",
    "Context Packet",
    "Evidence Packet",
    "NEXT_WORK_ORDER",
    "NEEDS_DECISION",
    "Decision Receipt",
    "UNVERIFIED",
}
FORBIDDEN_RUNTIME_PATTERNS = {
    "source-repository docs dependency": re.compile(
        r"(?:\.\./)+docs/|agent-project-system/docs/", re.IGNORECASE
    ),
    "legacy root packet dependency": re.compile(
        r"assets/packets/", re.IGNORECASE
    ),
    "absolute Windows user path": re.compile(
        r"[A-Za-z]:[\\/]Users[\\/][^\\/\s]+", re.IGNORECASE
    ),
    "absolute macOS user path": re.compile(r"/Users/[^/\s]+", re.IGNORECASE),
}


def parse_frontmatter(text: str) -> tuple[dict[str, str], str | None]:
    match = re.match(r"\A---\s*\n(.*?)\n---\s*\n", text, flags=re.DOTALL)
    if not match:
        return {}, "SKILL.md has no valid opening YAML frontmatter block"

    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if not line.strip():
            continue
        field = re.fullmatch(r"([A-Za-z0-9_-]+):\s*(.+)", line)
        if not field:
            return {}, f"unsupported frontmatter line: {line!r}"
        fields[field.group(1)] = field.group(2).strip().strip("'\"")
    return fields, None


def package_text_files() -> list[Path]:
    return sorted(
        path
        for path in PACKAGE.rglob("*")
        if path.is_file() and path.suffix.lower() in {".md", ".py", ".txt", ""}
    )


TRANSPORT_TEST_RUNNER = r"""
import importlib.util
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
test_path = Path(sys.argv[1])
result_path = Path(sys.argv[2])
token = sys.argv[3]
test_names = json.loads(sys.argv[4])
spec = importlib.util.spec_from_file_location("checked_transport_tests", test_path)
if spec is None or spec.loader is None:
    raise ImportError(f"cannot load transport tests from {test_path}")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
called = []
for name in test_names:
    test = getattr(module, name)
    if not callable(test):
        raise TypeError(f"discovered transport test is not callable: {name}")
    test()
    called.append(name)
result_path.write_text(
    json.dumps({"token": token, "called": called}), encoding="utf-8"
)
"""


def run_transport_tests(
    test_path: Path, *, timeout_seconds: float = 120
) -> tuple[int, list[str]]:
    """Discover and directly execute every supported transport test once."""
    errors: list[str] = []
    try:
        tree = ast.parse(test_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, SyntaxError) as error:
        return 0, [f"transport tests could not be discovered: {error}"]

    discovered = {
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name.startswith("test_")
    }
    unsupported_async = sorted(
        node.name
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name.startswith("test_")
    )
    discovered_count = len(discovered) + len(unsupported_async)
    if unsupported_async:
        return discovered_count, [
            "unsupported async transport tests: " + ", ".join(unsupported_async)
        ]
    if not discovered:
        return 0, ["transport test execution discovered zero test functions"]

    ordered_tests = sorted(discovered)
    token = secrets.token_hex(32)
    with tempfile.TemporaryDirectory(prefix="rr-transport-test-runner-") as directory:
        result_path = Path(directory) / "result.json"
        try:
            completed = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    "-c",
                    TRANSPORT_TEST_RUNNER,
                    str(test_path),
                    str(result_path),
                    token,
                    json.dumps(ordered_tests),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return len(discovered), [
                f"transport test execution timed out after {timeout_seconds:g} seconds"
            ]
        except OSError as error:
            return len(discovered), [f"transport test process could not start: {error}"]

        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip()
            return len(discovered), [
                f"transport test execution failed with exit code {completed.returncode}"
                + (f": {detail[-1000:]}" if detail else "")
            ]
        if not result_path.is_file():
            return len(discovered), ["transport test runner produced no completion result"]
        try:
            result = json.loads(result_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            return len(discovered), [f"transport test runner result is invalid: {error}"]
        if result != {"token": token, "called": ordered_tests}:
            return len(discovered), [
                "transport test runner result does not match discovered tests"
            ]

    return len(discovered), errors


def main() -> int:
    errors: list[str] = []
    executed_transport_test_count = 0

    if not PACKAGE.is_dir():
        errors.append(f"source package does not exist: {PACKAGE}")
    else:
        entries = list(PACKAGE.rglob("SKILL.md"))
        if len(entries) != 1:
            errors.append(f"expected exactly one SKILL.md, found {len(entries)}")
        actual_package_files = {
            path.relative_to(PACKAGE).as_posix()
            for path in PACKAGE.rglob("*")
            if path.is_file()
        }
        for relative in sorted(EXPECTED_PACKAGE_FILES - actual_package_files):
            errors.append(f"expected package file does not exist: {relative}")
        for relative in sorted(actual_package_files - EXPECTED_PACKAGE_FILES):
            errors.append(f"unexpected package file: {relative}")

    skill_text = ""
    if ENTRY.is_file():
        skill_text = ENTRY.read_text(encoding="utf-8")
        metadata, metadata_error = parse_frontmatter(skill_text)
        if metadata_error:
            errors.append(metadata_error)
        else:
            for key in ("name", "description"):
                if not metadata.get(key, "").strip():
                    errors.append(f"frontmatter field is missing or empty: {key}")
            if metadata.get("name") != PACKAGE.name:
                errors.append(
                    f"frontmatter name {metadata.get('name')!r} does not match "
                    f"directory {PACKAGE.name!r}"
                )
            unexpected = sorted(set(metadata) - {"name", "description"})
            if unexpected:
                errors.append(
                    "frontmatter contains unsupported fields: " + ", ".join(unexpected)
                )
    else:
        errors.append("required entry does not exist: SKILL.md")

    if not VERSION.is_file():
        errors.append("required VERSION file does not exist")
    else:
        version_text = VERSION.read_text(encoding="utf-8").strip()
        if not re.fullmatch(
            r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)",
            version_text,
        ):
            errors.append(f"VERSION is not simple SemVer: {version_text!r}")

    if not TRANSPORT_SCRIPT.is_file():
        errors.append("required transport wrapper does not exist: scripts/opencli_transport.py")
    else:
        try:
            ast.parse(TRANSPORT_SCRIPT.read_text(encoding="utf-8"))
        except SyntaxError as error:
            errors.append(f"transport wrapper has invalid Python syntax: {error}")

    if not TRANSPORT_TEST.is_file():
        errors.append("required pure-local transport test does not exist: scripts/test_opencli_transport.py")
    else:
        test_text = TRANSPORT_TEST.read_text(encoding="utf-8")
        try:
            ast.parse(test_text)
        except SyntaxError as error:
            errors.append(f"transport synthetic test has invalid Python syntax: {error}")
        for scenario in (
            "test_help_exposes_prepare_new",
            "test_help_exposes_require_existing_conversation",
            "test_old_conversation_to_new_and_empty_result",
            "test_real_empty_result_format_regression",
            "test_nonzero_exact_empty_result_code_verifies_blank_page",
            "test_empty_json_object_or_array_verifies_blank_page",
            "test_runtime_contains_required_a2p1_fields",
            "test_old_conversation_still_active_fails",
            "test_existing_messages_fail",
            "test_unknown_error_code_is_unparseable",
            "test_unparseable_output_blocks_before_send",
            "test_already_new_reports_no_conversation_transition",
            "test_required_existing_from_new_stops_before_new",
            "test_required_existing_from_root_stops_before_new",
            "test_required_existing_rejects_invalid_conversation_url",
            "test_prepare_without_requirement_remains_compatible",
            "test_old_conversation_reports_verified_transition",
            "test_all_read_failures_remain_zero_send",
            "test_sixty_second_budget_is_machine_enforced",
            "test_prepare_never_calls_ask_or_send",
            "test_external_command_budget_stops_before_next_command",
            "test_real_conversation_url_can_execute",
            "test_angle_id_placeholder_is_rejected",
            "test_chinese_paste_placeholder_is_rejected",
            "test_empty_required_value_is_rejected",
            "test_placeholder_failure_has_zero_external_commands",
            "test_send_placeholder_is_blocked_before_opencli",
            "test_send_help_exposes_integrated_prepare_new",
            "test_start_new_and_send_completes_in_one_wrapper_call",
            "test_start_new_and_send_uses_one_bounded_recovery_when_needed",
            "test_synchronous_status_terminates_immediately",
            "test_schedule_after_synchronous_result_is_protocol_violation",
            "test_two_second_foreground_trace_is_synchronous",
            "test_seven_second_foreground_trace_is_synchronous",
            "test_background_wait_without_handle_is_rejected",
            "test_bound_background_result_is_read_once_within_fifteen_seconds",
            "test_background_completion_is_not_synchronous_completion",
            "test_schedule_call_cannot_report_zero_wait",
            "test_protocol_violation_cannot_return_pass",
            "test_contradictory_report_fails_validation",
            "test_unauthorized_sleep_is_protocol_violation",
            "test_poll_requires_authorized_running_job",
            "test_all_experiment_actions_are_counted",
            "test_prepare_and_send_use_one_shared_read_classifier",
            "test_send_manual_real_empty_result_sends_once_without_new",
            "test_send_manual_existing_messages_block_without_send",
            "test_send_manual_unknown_error_blocks_without_send",
            "test_send_manual_unparseable_output_blocks_without_send",
            "test_ask_yaml_explicit_conversation_id_is_accepted",
            "test_ask_yaml_body_cannot_spoof_identity_or_ready_response",
            "test_ask_identity_rejects_mismatch_and_non_chatgpt_url",
            "test_ask_without_id_status_new_id_uses_post_history_and_exact_detail",
            "test_status_without_id_uses_single_new_history_candidate",
            "test_new_history_candidate_requires_both_exact_identifiers",
            "test_new_history_candidate_without_identifiers_stays_unknown",
            "test_work_item_only_without_message_id_stays_unknown",
            "test_message_id_prefix_collision_does_not_match",
            "test_work_item_id_prefix_collision_does_not_match",
            "test_post_send_history_unavailable_uses_status_target_once",
            "test_recovery_and_detail_budgets_remain_one",
            "test_detail_count_only_increments_on_real_invocation",
            "test_multiple_new_history_candidates_stay_unknown_without_detail",
            "test_existing_conversation_recovery_is_not_misroute",
            "test_visible_schedule_missing_from_agent_count_fails_validation",
            "test_wrapper_zero_does_not_replace_agent_schedule_count",
            "test_unavailable_agent_trace_does_not_claim_zero_total",
            "test_protocol_violation_cannot_meet_experiment_acceptance",
            "test_delivery_unknown_report_must_forbid_same_id_resend",
            "test_report_requires_explicit_agent_trace_fields",
            "test_report_rejects_unknown_agent_trace_verification",
            "test_rr_response_exact_identity_is_accepted",
            "test_response_source_is_bound_to_detail_result",
            "test_accept_delivery_cannot_overwrite_verified_target",
            "test_wrong_messages_cannot_be_paired_with_expected_conversation",
            "test_duplicate_outbound_messages_are_ambiguous",
            "test_duplicate_outbound_identity_cannot_enter_official_parser",
            "test_exact_rr_review_envelope_is_accepted",
            "test_assistant_quoted_rr_review_is_rejected",
            "test_rr_review_with_leading_text_is_rejected",
            "test_rr_review_with_trailing_text_is_rejected",
            "test_rr_review_missing_begin_marker_is_rejected",
            "test_rr_review_missing_end_marker_is_rejected",
            "test_rr_response_wrong_work_item_is_rejected",
            "test_rr_response_wrong_in_reply_to_message_is_rejected",
            "test_rr_response_wrong_round_is_rejected",
            "test_rr_response_missing_identity_field_is_rejected",
            "test_rr_response_work_item_prefix_collision_is_rejected",
            "test_rr_response_message_id_prefix_collision_is_rejected",
            "test_user_quoted_rr_response_is_not_accepted",
            "test_old_round_response_before_target_message_is_not_accepted",
            "test_correct_response_from_wrong_conversation_is_rejected",
            "test_multiple_matching_rr_responses_are_ambiguous",
            "test_identity_failure_does_not_allow_same_message_id_resend",
        ):
            if scenario not in test_text:
                errors.append(f"transport synthetic test is missing scenario: {scenario}")

        prepare_body = re.search(
            r"def prepare_new_command\(.*?\n(?=def prepare_payload\()",
            TRANSPORT_SCRIPT.read_text(encoding="utf-8") if TRANSPORT_SCRIPT.is_file() else "",
            flags=re.DOTALL,
        )
        if not prepare_body:
            errors.append("transport wrapper has no inspectable prepare_new_command")
        elif re.search(r'\[\s*"chatgpt"\s*,\s*"(?:ask|send)"', prepare_body.group(0)):
            errors.append("prepare_new_command contains a prohibited ask/send OpenCLI call")

        executed_transport_test_count, execution_errors = run_transport_tests(TRANSPORT_TEST)
        errors.extend(execution_errors)

    asset_dir = PACKAGE / "assets"
    actual_assets = (
        {path.name for path in asset_dir.glob("*.md")} if asset_dir.is_dir() else set()
    )
    for name in sorted(REQUIRED_ASSETS - actual_assets):
        errors.append(f"required asset does not exist: assets/{name}")
    for name in sorted(actual_assets - REQUIRED_ASSETS):
        errors.append(f"unexpected Markdown asset: assets/{name}")

    referenced_assets = set(re.findall(r"`(assets/[a-z0-9-]+\.md)`", skill_text))
    expected_references = {f"assets/{name}" for name in REQUIRED_ASSETS}
    for relative in sorted(expected_references - referenced_assets):
        errors.append(f"SKILL.md does not reference required asset: {relative}")
    for relative in sorted(referenced_assets):
        if not (PACKAGE / relative).is_file():
            errors.append(f"SKILL.md references missing package resource: {relative}")

    for path in package_text_files() if PACKAGE.is_dir() else []:
        text = path.read_text(encoding="utf-8")
        relative = path.relative_to(PACKAGE).as_posix()
        for label, pattern in FORBIDDEN_RUNTIME_PATTERNS.items():
            if pattern.search(text):
                errors.append(f"{relative} contains forbidden {label}")

    if skill_text:
        for marker in sorted(REQUIRED_SKILL_MARKERS):
            if marker not in skill_text:
                errors.append(f"SKILL.md is missing required loop marker: {marker}")
        if not re.search(
            r"must never impersonate the Browser RR Lead|不得冒充 Browser RR Lead",
            skill_text,
            flags=re.IGNORECASE,
        ):
            errors.append("SKILL.md does not prohibit IDE-side RR Lead impersonation")
        if not re.search(r"Git is not used|Git is not applicable", skill_text):
            errors.append("SKILL.md does not explicitly support projects without Git")
        if re.search(
            r"(?:must|required to|always)\s+(?:provide|include|use).*Git (?:diff|evidence)",
            skill_text,
            flags=re.IGNORECASE,
        ):
            errors.append("SKILL.md appears to require Git evidence for every project")

    legacy_assets = ROOT / "assets" / "packets"
    if legacy_assets.exists() and any(legacy_assets.rglob("*.md")):
        errors.append("legacy assets/packets Markdown templates still exist")

    for name in REQUIRED_ASSETS:
        copies = [
            path
            for path in ROOT.rglob(name)
            if ".git" not in path.relative_to(ROOT).parts
        ]
        if len(copies) != 1:
            listed = ", ".join(path.relative_to(ROOT).as_posix() for path in copies)
            errors.append(f"expected one authoritative {name}, found {len(copies)}: {listed}")

    ds_store = [
        path
        for path in PACKAGE.rglob(".DS_Store")
        if path.is_file()
    ] if PACKAGE.is_dir() else []
    for path in ds_store:
        errors.append(f"package contains .DS_Store: {path.relative_to(PACKAGE)}")

    generated_python = [
        path
        for path in PACKAGE.rglob("*")
        if path.is_file()
        and (path.suffix.lower() in {".pyc", ".pyo"} or "__pycache__" in path.parts)
    ] if PACKAGE.is_dir() else []
    for path in generated_python:
        errors.append(
            f"package contains generated Python cache: {path.relative_to(PACKAGE)}"
        )

    if errors:
        print("Skill package checks failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print(f"Skill package checks passed: {PACKAGE.relative_to(ROOT).as_posix()}")
    print("Entry: one valid SKILL.md with matching name and description.")
    print(f"Version: {VERSION.read_text(encoding='utf-8').strip()} (simple SemVer).")
    print("Assets: five required files, each with one authoritative copy.")
    print("Transport structure: wrapper syntax and required package markers validated.")
    print(
        "Transport tests: "
        f"executed {executed_transport_test_count} discovered pure-local tests; "
        "the controlled runner called every test exactly once without exceptions."
    )
    print("Loop contract: roles, Goal Contract, delivery state, conversation identity, and HITL markers exist.")
    print("Portability: referenced resources exist; no forbidden runtime dependencies found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
