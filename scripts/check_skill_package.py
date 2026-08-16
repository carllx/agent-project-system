"""Validate the self-contained Research Review Lead source skill package."""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "skills" / "research-review-lead"
ENTRY = PACKAGE / "SKILL.md"
VERSION = PACKAGE / "VERSION"
TRANSPORT_SCRIPT = PACKAGE / "scripts" / "opencli_transport.py"
MINIMAL_BRIDGE_SCRIPT = PACKAGE / "scripts" / "minimal_bridge.py"
MINIMAL_BRIDGE_TEST = ROOT / "scripts" / "test_minimal_review_bridge.py"

REQUIRED_ASSETS = {
    "context-packet.md",
    "evidence-packet.md",
    "decision-request.md",
    "handoff.md",
    "rr-lead-init.md",
}
REQUIRED_RR_INIT_MARKERS = {
    "exactly one fenced `text` code block",
    "put no text before or after that block",
    "Do not normalize, dedent, repair, or convert",
}

EXPECTED_PACKAGE_FILES = {
    "SKILL.md",
    "VERSION",
    "scripts/opencli_transport.py",
    "scripts/minimal_bridge.py",
    *(f"assets/{name}" for name in REQUIRED_ASSETS),
}

REQUIRED_SKILL_MARKERS = {
    "Builder IDE Agent",
    "IDE-side Loop Driver",
    "Browser RR Lead",
    "OpenCLI",
    "EXPLICIT_SELECTION_BOOTSTRAP_GATE",
    "PRECHECK_IS_NOT_BOOTSTRAP",
    "NO_DOMAIN_WORK_BEFORE_BOOTSTRAP",
    "NO_LOCAL_BROWSER_REVIEW_SUBSTITUTE",
    "DELIVERY_STATE",
    "RESPONSE_PENDING",
    "RESPONSE_READY",
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


def check_package_layout() -> list[str]:
    errors: list[str] = []
    if not PACKAGE.is_dir():
        errors.append(f"source package does not exist: {PACKAGE}")
    else:
        entries = list(PACKAGE.rglob("SKILL.md"))
        if len(entries) != 1:
            errors.append(f"expected exactly one SKILL.md, found {len(entries)}")
        actual_package_files = {
            path.relative_to(PACKAGE).as_posix()
            for path in PACKAGE.rglob("*")
            if path.is_file() and "__pycache__" not in path.parts and path.suffix.lower() not in {".pyc", ".pyo"}
        }
        for relative in sorted(EXPECTED_PACKAGE_FILES - actual_package_files):
            errors.append(f"expected package file does not exist: {relative}")
        for relative in sorted(actual_package_files - EXPECTED_PACKAGE_FILES):
            errors.append(f"unexpected package file: {relative}")
    return errors


def check_skill_entry_and_version() -> tuple[str, list[str]]:
    errors: list[str] = []
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
    return skill_text, errors


def check_transport_package() -> list[str]:
    errors: list[str] = []
    for script_path in [TRANSPORT_SCRIPT, MINIMAL_BRIDGE_SCRIPT]:
        if not script_path.is_file():
            errors.append(f"required script does not exist: {script_path.relative_to(ROOT).as_posix()}")
        else:
            try:
                ast.parse(script_path.read_text(encoding="utf-8"))
            except SyntaxError as error:
                errors.append(f"{script_path.name} has invalid Python syntax: {error}")

    if not MINIMAL_BRIDGE_TEST.is_file():
        errors.append("required minimal bridge test does not exist: scripts/test_minimal_review_bridge.py")
    else:
        try:
            completed = subprocess.run(
                [sys.executable, "-B", "-m", "unittest", "scripts/test_minimal_review_bridge.py"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            if completed.returncode != 0:
                errors.append(f"test_minimal_review_bridge.py failed: {completed.stderr or completed.stdout}")
        except Exception as exc:
            errors.append(f"failed to run test_minimal_review_bridge.py: {exc}")

    return errors


def check_assets_and_references(skill_text: str) -> list[str]:
    errors: list[str] = []
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
    rr_init = asset_dir / "rr-lead-init.md"
    if rr_init.is_file():
        rr_init_text = rr_init.read_text(encoding="utf-8")
        for marker in sorted(REQUIRED_RR_INIT_MARKERS):
            if marker not in rr_init_text:
                errors.append(
                    "rr-lead-init.md is missing fenced response contract marker: "
                    f"{marker}"
                )
    return errors


def check_portability_and_contract(skill_text: str) -> list[str]:
    errors: list[str] = []
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
    return errors


def check_repository_hygiene() -> list[str]:
    errors: list[str] = []
    legacy_assets = ROOT / "assets" / "packets"
    if legacy_assets.exists() and any(legacy_assets.rglob("*.md")):
        errors.append("legacy assets/packets Markdown templates still exist")

    for name in REQUIRED_ASSETS:
        copies = [
            path
            for path in ROOT.rglob(name)
            if ".git" not in path.relative_to(ROOT).parts
            and ".agents" not in path.relative_to(ROOT).parts
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
    return errors


def main() -> int:
    errors: list[str] = []
    errors.extend(check_package_layout())
    skill_text, entry_and_version_errors = check_skill_entry_and_version()
    errors.extend(entry_and_version_errors)
    errors.extend(check_transport_package())
    errors.extend(check_assets_and_references(skill_text))
    errors.extend(check_portability_and_contract(skill_text))
    errors.extend(check_repository_hygiene())

    if errors:
        print("Skill package checks failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print(f"Skill package checks passed: {PACKAGE.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
