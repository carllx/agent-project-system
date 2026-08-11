"""Validate the repository's closed Markdown knowledge system."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "docs" / "index.md"
ALLOWED_ROOT = {"AGENTS.md", "README.md", "CLAUDE.md"}
GARBAGE_WORDS = {"v2", "final", "backup", "old"}
ACTIVE_PACKET_POINTER = ROOT / "docs" / "references" / "current-execution-packet.md"
CURRENT_STATE = ROOT / "docs" / "current.md"


def markdown_files() -> list[Path]:
    return sorted(
        path
        for path in ROOT.rglob("*.md")
        if ".git" not in path.relative_to(ROOT).parts
    )


def is_allowed(path: Path) -> bool:
    relative = path.relative_to(ROOT)
    parts = relative.parts
    if len(parts) == 1:
        return relative.as_posix() in ALLOWED_ROOT
    if relative.as_posix() in {"docs/index.md", "docs/current.md"}:
        return True
    if len(parts) == 3 and parts[0] == "docs" and parts[1] in {
        "specs",
        "adr",
        "references",
    }:
        return True
    if len(parts) == 3 and parts[0] == "skills" and parts[2] == "SKILL.md":
        return True
    return (
        len(parts) == 4
        and parts[0] == "skills"
        and parts[2] == "assets"
    )


def garbage_reason(path: Path) -> str | None:
    relative = path.relative_to(ROOT).as_posix()
    lowered = relative.lower()
    tokens = set(re.findall(r"[a-z0-9]+", lowered))
    found = sorted(tokens & GARBAGE_WORDS)
    if found:
        return f"garbage version word: {', '.join(found)}"
    if re.search(r"\d{4}[-_]\d{2}[-_]\d{2}", lowered):
        return "dated Markdown copy"
    compact = re.sub(r"[^a-z0-9]", "", lowered)
    if "sessionsummary" in compact or "nextsteps" in compact:
        return "temporary summary/next-steps document"
    if (
        "handoff" in lowered
        and not re.fullmatch(r"skills/[^/]+/assets/handoff\.md", relative)
    ):
        return "actual or duplicate handoff document"
    return None


def registered_paths() -> list[str]:
    if not INDEX.exists():
        return []
    text = INDEX.read_text(encoding="utf-8")
    return re.findall(r"^\| `([^`]+\.md)` \|", text, flags=re.MULTILINE)


def tracked_paths() -> tuple[set[str], str | None]:
    try:
        result = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=ROOT,
            capture_output=True,
            check=False,
        )
    except OSError as error:
        return set(), f"git ls-files could not run: {error}"
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace").strip()
        detail = f": {stderr}" if stderr else ""
        return set(), f"git ls-files failed with exit code {result.returncode}{detail}"
    return (
        {
            item.decode("utf-8", errors="replace")
            for item in result.stdout.split(b"\0")
            if item
        },
        None,
    )


def scalar_fields(text: str) -> dict[str, str]:
    return {
        key: value.strip()
        for key, value in re.findall(r"^([A-Z][A-Z0-9_]+):\s*(.+)$", text, re.MULTILINE)
    }


def validate_active_execution_packet(errors: list[str]) -> None:
    if not ACTIVE_PACKET_POINTER.exists():
        errors.append("active Execution Packet pointer does not exist")
        return
    pointer_text = ACTIVE_PACKET_POINTER.read_text(encoding="utf-8")
    pointer_matches = re.findall(
        r"^([A-Z][A-Z0-9_]+):\s*(.+)$", pointer_text, re.MULTILINE
    )
    pointer = {key: value.strip() for key, value in pointer_matches}
    required_pointer_fields = {
        "ACTIVE_WORK_ITEM",
        "ACTIVE_EXECUTION_PACKET",
        "PACKET_STATE",
        "REQUIRED_PRODUCT_HEAD",
        "ACTIVE_PACKET_SHA256",
    }
    if len(pointer_matches) != len(required_pointer_fields) or set(pointer) != required_pointer_fields:
        errors.append("active Execution Packet pointer must contain only the five pointer fields")
        return
    packet_relative = pointer["ACTIVE_EXECUTION_PACKET"]
    packet_path = (ROOT / packet_relative).resolve()
    if not packet_path.is_relative_to(ROOT):
        errors.append("active Execution Packet path escapes the repository")
        return
    if not packet_path.is_file():
        errors.append(f"active Execution Packet does not exist: {packet_relative}")
        return
    packet_bytes = packet_path.read_bytes()
    packet_text = packet_bytes.decode("utf-8")
    packet = scalar_fields(packet_text)
    if packet.get("WORK_ITEM_ID") != pointer["ACTIVE_WORK_ITEM"]:
        errors.append("active Execution Packet Work Item does not match its pointer")
    if packet.get("REQUIRED_PRODUCT_HEAD") != pointer["REQUIRED_PRODUCT_HEAD"]:
        errors.append("active Execution Packet required Product head does not match its pointer")
    allowed_packet_states = {"READY_NOT_STARTED", "BLOCKED_NOT_READY"}
    if (
        pointer["PACKET_STATE"] not in allowed_packet_states
        or packet.get("PACKET_STATE") != pointer["PACKET_STATE"]
    ):
        errors.append("active Execution Packet state is invalid or does not match its pointer")
    canonical_packet_bytes = packet_text.replace("\r\n", "\n").encode("utf-8")
    actual_hash = hashlib.sha256(canonical_packet_bytes).hexdigest()
    if pointer["ACTIVE_PACKET_SHA256"] != actual_hash:
        errors.append("active Execution Packet SHA-256 does not match its pointer")
    if not re.fullmatch(r"[0-9a-f]{40}", pointer["REQUIRED_PRODUCT_HEAD"]):
        errors.append("active Execution Packet required Product head is not an exact Git SHA")
    current_text = CURRENT_STATE.read_text(encoding="utf-8")
    if f"**ID:** `{pointer['ACTIVE_WORK_ITEM']}`" not in current_text:
        errors.append("docs/current.md active Work Item does not match the Packet pointer")
    if "**ACTIVE_EXECUTION_PACKET_POINTER:** `docs/references/current-execution-packet.md`" not in current_text:
        errors.append("docs/current.md does not identify the stable active Packet pointer")
    current_packet_state = {
        "READY_NOT_STARTED": "**Execution Packet state:** `READY / NOT_STARTED`",
        "BLOCKED_NOT_READY": "**Execution Packet state:** `BLOCKED / NOT READY`",
    }[pointer["PACKET_STATE"]]
    if current_packet_state not in current_text:
        errors.append("docs/current.md does not record the active Packet state")
    forbidden = ("transcript.jsonl", ".gemini\\antigravity\\brain")
    if any(value.lower() in packet_text.lower() for value in forbidden):
        errors.append("active Execution Packet depends on forbidden historical conversation sources")
    if re.search(r"&(?:amp|lt|gt|quot|#\d+);", packet_text):
        errors.append("active Execution Packet contains escaped HTML/CLI garbage")
    if packet.get("PACKET_TYPE") == "REAL_AGENT_REVIEW_LOOP_MANUAL_RELAY_PACKET":
        forbidden_automatic_tokens = (
            "opencli_transport.py",
            "send-review",
            "recover-review",
            "--prepare-new",
            "--previous-transport-state",
        )
        automatic_cli_call = re.search(
            r"(?im)^\s*(?:opencli(?:\.exe)?\s|python\s+\S*opencli_transport\.py\s)",
            packet_text,
        )
        if automatic_cli_call or any(
            token in packet_text.lower() for token in forbidden_automatic_tokens
        ):
            errors.append("Manual Relay Packet contains an automatic Transport command")
        readiness = packet.get("MANUAL_RELAY_ACCEPTANCE_READY")
        if pointer["PACKET_STATE"] == "BLOCKED_NOT_READY" and readiness != "NO":
            errors.append("blocked Manual Relay Packet must record readiness NO")
        if pointer["PACKET_STATE"] == "READY_NOT_STARTED":
            if readiness != "YES":
                errors.append("ready Manual Relay Packet must record readiness YES")
            required_manual_tokens = (
                "ingest-manual-review",
                "--response-presentation COPY_SAFE_PLAIN_TEXT_BLOCK",
                "BROWSER_RESPONSE_PRESENTATION: COPY_SAFE_PLAIN_TEXT_BLOCK",
                "R1_BROWSER_RELAY_PACKET",
                "R2_BROWSER_RELAY_PACKET",
                "r1-browser-response.txt",
                "r2-browser-response.txt",
                "REVIEW_SOURCE=MANUAL_RELAY",
                "GATE_A_BROWSER_FINAL_REVIEW",
                "GATE_B_POST_INGEST_COMPLETION_VERIFICATION",
                "R1_RAW_RESPONSE_SHA256",
                "R2_INPUT.UNRESOLVED_USER_DECISION",
                "POST_INGEST_4",
                "POST_INGEST_COMPLETION_FAILURE",
                "AUTOMATED_BROWSER_TRANSPORT_VALIDATED: NO",
                "Exactly four user copy steps",
            )
            if any(token not in packet_text for token in required_manual_tokens):
                errors.append("ready Manual Relay Packet is missing an executable relay/ingest requirement")
            circular_browser_criteria = (
                "R2 is relayed once and strictly ingested as authoritative `APPROVE`",
                "both raw Browser responses are preserved byte-for-byte",
                "Completion Gate reaches `COMPLETED` only after the current matching Final approval",
            )
            if any(token in packet_text for token in circular_browser_criteria):
                errors.append("Manual Relay Browser criteria contain a post-ingest circular dependency")
    if packet.get("PACKET_TYPE") == "DIAGNOSTIC_BATCH_PACKET":
        batch_id = packet.get("BATCH_ID")
        if not batch_id or f"**Active Diagnostic Batch:** `{batch_id}`" not in current_text:
            errors.append("docs/current.md active Diagnostic Batch does not match its Packet")
        schema_relative = packet.get("EVIDENCE_MATRIX_SCHEMA")
        if not schema_relative:
            errors.append("Diagnostic Batch Packet has no Evidence Matrix schema")
            return
        schema_path = (ROOT / schema_relative).resolve()
        if not schema_path.is_relative_to(ROOT) or not schema_path.is_file():
            errors.append("Diagnostic Batch Evidence Matrix schema is missing or outside the repository")
            return
        try:
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            errors.append(f"Diagnostic Batch Evidence Matrix schema is invalid JSON: {error}")
            return
        batch_const = schema.get("properties", {}).get("BATCH_ID", {}).get("const")
        if batch_const != batch_id:
            errors.append("Diagnostic Batch Evidence Matrix schema has the wrong Batch identity")
        budget_properties = (
            schema.get("properties", {}).get("BUDGET", {}).get("properties", {})
        )
        for field in (
            "MAX_HYPOTHESES",
            "MAX_RUNTIME_PROBES",
            "MAX_BROWSER_WRITES",
            "MAX_SHARED_RUNTIME_WRITES",
            "MAX_SUBAGENTS",
            "MAX_BATCH_ROUNDS",
            "MAX_WALLCLOCK_MINUTES",
        ):
            if str(budget_properties.get(field, {}).get("const")) != packet.get(field):
                errors.append(f"Diagnostic Batch budget mismatch for {field}")


def main() -> int:
    errors: list[str] = []
    files = markdown_files()
    validate_active_execution_packet(errors)

    agents_lines = (ROOT / "AGENTS.md").read_text(encoding="utf-8").splitlines()
    if len(agents_lines) > 100:
        errors.append(f"AGENTS.md has {len(agents_lines)} physical lines; maximum is 100")

    for path in files:
        relative = path.relative_to(ROOT).as_posix()
        if not is_allowed(path):
            errors.append(f"disallowed Markdown path: {relative}")
        reason = garbage_reason(path)
        if reason:
            errors.append(f"disallowed Markdown name: {relative} ({reason})")

    registered = registered_paths()
    registered_set = set(registered)
    if len(registered) != len(registered_set):
        errors.append("docs/index.md contains duplicate Markdown registrations")

    actual_set = {path.relative_to(ROOT).as_posix() for path in files}
    for relative in sorted(actual_set - registered_set):
        errors.append(f"Markdown is not registered in docs/index.md: {relative}")
    for relative in sorted(registered_set - actual_set):
        errors.append(f"registered Markdown does not exist: {relative}")

    ds_store_paths = sorted(
        path.relative_to(ROOT).as_posix()
        for path in ROOT.rglob(".DS_Store")
        if ".git" not in path.relative_to(ROOT).parts
    )
    for relative in ds_store_paths:
        errors.append(f".DS_Store exists in project: {relative}")
    tracked, git_error = tracked_paths()
    if git_error:
        errors.append(git_error)
    elif any(Path(path).name == ".DS_Store" for path in tracked):
        errors.append("Git tracks at least one .DS_Store")

    claude = ROOT / "CLAUDE.md"
    if claude.exists() and claude.read_text(encoding="utf-8").strip() != "@AGENTS.md":
        errors.append("CLAUDE.md may contain only @AGENTS.md")

    if errors:
        print("Documentation checks failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print(f"Documentation checks passed: {len(files)} Markdown files registered.")
    print(f"AGENTS.md physical lines: {len(agents_lines)}/100.")
    print("No disallowed paths, garbage copies, or .DS_Store files found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
