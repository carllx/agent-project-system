"""Validate the repository's closed Markdown knowledge system."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "docs" / "index.md"
ALLOWED_ROOT = {"AGENTS.md", "README.md", "CLAUDE.md"}
GARBAGE_WORDS = {"v2", "final", "backup", "old"}


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
    return len(parts) == 3 and parts[:2] == ("assets", "packets")


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
    if "handoff" in lowered and relative != "assets/packets/handoff.md":
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


def main() -> int:
    errors: list[str] = []
    files = markdown_files()

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
