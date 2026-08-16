"""Install or verify the repository-source RR Lead Skill runtime copy."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "skills" / "research-review-lead"
DEFAULT_TARGET = ROOT / ".agents" / "skills" / "research-review-lead"
PACKAGE_FILES = (
    "SKILL.md",
    "VERSION",
    "assets/context-packet.md",
    "assets/decision-request.md",
    "assets/evidence-packet.md",
    "assets/handoff.md",
    "assets/rr-lead-init.md",
    "scripts/minimal_bridge.py",
    "scripts/opencli_transport.py",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def declared_snapshot(root: Path) -> dict[str, str]:
    missing = [relative for relative in PACKAGE_FILES if not (root / relative).is_file()]
    if missing:
        raise ValueError(f"declared runtime files are missing: {', '.join(missing)}")
    return {relative: sha256(root / relative) for relative in PACKAGE_FILES}


def unexpected_runtime_files(root: Path) -> list[str]:
    if not root.exists():
        return []
    declared = set(PACKAGE_FILES)
    return sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix.lower() not in {".pyc", ".pyo"}
        and path.relative_to(root).as_posix() not in declared
    )


def sync_runtime(source: Path, target: Path, check_only: bool = False) -> dict[str, object]:
    source = source.resolve()
    target = target.resolve()
    source_hashes = declared_snapshot(source)
    before_version = (
        (target / "VERSION").read_text(encoding="utf-8").strip()
        if (target / "VERSION").is_file()
        else "MISSING"
    )
    extras = unexpected_runtime_files(target)
    if extras:
        raise ValueError(f"runtime target contains unknown files: {', '.join(extras)}")
    if not check_only:
        for relative in PACKAGE_FILES:
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_name(f".{destination.name}.sync-{os.getpid()}")
            try:
                shutil.copy2(source / relative, temporary)
                os.replace(temporary, destination)
            finally:
                if temporary.exists():
                    temporary.unlink()
    target_hashes = declared_snapshot(target)
    mismatches = [
        relative
        for relative in PACKAGE_FILES
        if source_hashes[relative] != target_hashes[relative]
    ]
    source_version = (source / "VERSION").read_text(encoding="utf-8").strip()
    target_version = (target / "VERSION").read_text(encoding="utf-8").strip()
    if source_version != target_version or mismatches:
        raise ValueError(
            "runtime parity failed: "
            f"source_version={source_version}, target_version={target_version}, "
            f"hash_mismatches={','.join(mismatches) or 'NONE'}"
        )
    return {
        "source": str(source),
        "target": str(target),
        "runtime_version_before": before_version,
        "runtime_version_after": target_version,
        "file_count": len(PACKAGE_FILES),
        "hash_parity": True,
        "check_only": check_only,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="One-way sync and SHA-256 parity check for the RR Lead runtime copy."
    )
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    try:
        report = sync_runtime(args.source, args.target, args.check_only)
    except (OSError, ValueError) as error:
        print(f"Runtime skill sync failed: {error}")
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
