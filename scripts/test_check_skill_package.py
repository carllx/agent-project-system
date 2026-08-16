"""Regression tests for package-checker execution integrity."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "scripts" / "check_skill_package.py"
SPEC = importlib.util.spec_from_file_location("check_skill_package", CHECKER)
assert SPEC and SPEC.loader
CHECKER_MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER_MODULE)
SYNC_SCRIPT = ROOT / "scripts" / "sync_skill_runtime.py"
SYNC_SPEC = importlib.util.spec_from_file_location("sync_skill_runtime", SYNC_SCRIPT)
assert SYNC_SPEC and SYNC_SPEC.loader
SYNC_MODULE = importlib.util.module_from_spec(SYNC_SPEC)
SYNC_SPEC.loader.exec_module(SYNC_MODULE)


class PackageCheckerExecutionTests(unittest.TestCase):
    def make_runtime_package(self, root: Path, version: str) -> Path:
        package = root / "research-review-lead"
        for relative in SYNC_MODULE.PACKAGE_FILES:
            path = package / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                f"{version}\n" if relative == "VERSION" else f"{relative}:{version}\n",
                encoding="utf-8",
            )
        return package

    def test_runtime_sync_updates_version_and_all_declared_hashes(self) -> None:
        with tempfile.TemporaryDirectory(prefix="runtime-sync-test-") as directory:
            root = Path(directory)
            source = self.make_runtime_package(root / "source", "0.4.21")
            target = self.make_runtime_package(root / "target", "0.4.14")

            report = SYNC_MODULE.sync_runtime(source, target)

            self.assertEqual(report["runtime_version_before"], "0.4.14")
            self.assertEqual(report["runtime_version_after"], "0.4.21")
            self.assertTrue(report["hash_parity"])
            self.assertEqual(
                SYNC_MODULE.declared_snapshot(source),
                SYNC_MODULE.declared_snapshot(target),
            )

    def test_runtime_sync_refuses_unknown_target_files(self) -> None:
        with tempfile.TemporaryDirectory(prefix="runtime-sync-extra-test-") as directory:
            root = Path(directory)
            source = self.make_runtime_package(root / "source", "0.4.21")
            target = self.make_runtime_package(root / "target", "0.4.14")
            (target / "unknown.txt").write_text("do not overwrite\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "unknown files"):
                SYNC_MODULE.sync_runtime(source, target)

            self.assertEqual((target / "VERSION").read_text(encoding="utf-8"), "0.4.14\n")

    def test_runtime_check_only_rejects_hash_mismatch(self) -> None:
        with tempfile.TemporaryDirectory(prefix="runtime-check-test-") as directory:
            root = Path(directory)
            source = self.make_runtime_package(root / "source", "0.4.21")
            target = self.make_runtime_package(root / "target", "0.4.21")
            (target / "SKILL.md").write_text("stale\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "hash_mismatches=SKILL.md"):
                SYNC_MODULE.sync_runtime(source, target, check_only=True)

    def test_rr_lead_init_enforces_fenced_machine_response_contract(self) -> None:
        rr_init = (
            ROOT / "skills" / "research-review-lead" / "assets" / "rr-lead-init.md"
        ).read_text(encoding="utf-8")
        for marker in CHECKER_MODULE.REQUIRED_RR_INIT_MARKERS:
            self.assertIn(marker, rr_init)

    def test_explicit_skill_selection_requires_bootstrap_before_domain_work(self) -> None:
        skill_text = (ROOT / "skills" / "research-review-lead" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        required_invocation_markers = [
            "EXPLICIT_SELECTION_BOOTSTRAP_GATE",
            "PRECHECK_IS_NOT_BOOTSTRAP",
            "NO_DOMAIN_WORK_BEFORE_BOOTSTRAP",
            "NO_LOCAL_BROWSER_REVIEW_SUBSTITUTE",
        ]
        for marker in required_invocation_markers:
            self.assertIn(
                marker,
                skill_text,
                f"SKILL.md missing explicit invocation gate marker: {marker}",
            )

    def test_repository_hygiene_ignores_agents_runtime_deployment_copy(self) -> None:
        with tempfile.TemporaryDirectory(prefix="runtime-hygiene-test-") as directory:
            root = Path(directory)
            package = root / "skills" / "research-review-lead"
            runtime = root / ".agents" / "skills" / "research-review-lead"
            for asset in CHECKER_MODULE.REQUIRED_ASSETS:
                for destination in (package / "assets" / asset, runtime / "assets" / asset):
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_text("fixture\n", encoding="utf-8")

            with mock.patch.multiple(CHECKER_MODULE, ROOT=root, PACKAGE=package):
                errors = CHECKER_MODULE.check_repository_hygiene()

            self.assertFalse(
                any("expected one authoritative" in error for error in errors), errors
            )

    def test_main_failure_exit_code_is_preserved(self) -> None:
        stdout = io.StringIO()
        with mock.patch.object(
            CHECKER_MODULE,
            "check_package_layout",
            return_value=["synthetic package failure"],
        ), contextlib.redirect_stdout(stdout):
            exit_code = CHECKER_MODULE.main()

        self.assertEqual(exit_code, 1)
        self.assertTrue(
            stdout.getvalue().startswith(
                "Skill package checks failed:\n- synthetic package failure\n"
            )
        )

    def test_multiple_errors_preserve_original_order(self) -> None:
        with tempfile.TemporaryDirectory(prefix="checker-multi-error-") as directory:
            root = Path(directory)
            package = root / "skills" / "research-review-lead"
            package.mkdir(parents=True)
            (package / "unexpected.txt").write_text("fixture\n", encoding="utf-8")
            replacements = {
                "ROOT": root,
                "PACKAGE": package,
                "ENTRY": package / "SKILL.md",
                "VERSION": package / "VERSION",
                "TRANSPORT_SCRIPT": package / "scripts" / "opencli_transport.py",
                "MINIMAL_BRIDGE_SCRIPT": package / "scripts" / "minimal_bridge.py",
                "MINIMAL_BRIDGE_TEST": root / "scripts" / "test_minimal_review_bridge.py",
            }
            stdout = io.StringIO()
            with mock.patch.multiple(
                CHECKER_MODULE, **replacements
            ), contextlib.redirect_stdout(stdout):
                exit_code = CHECKER_MODULE.main()

        expected_errors = [
            "expected exactly one SKILL.md, found 0",
            *(
                f"expected package file does not exist: {relative}"
                for relative in sorted(CHECKER_MODULE.EXPECTED_PACKAGE_FILES)
            ),
            "unexpected package file: unexpected.txt",
            "required entry does not exist: SKILL.md",
            "required VERSION file does not exist",
            "required script does not exist: skills/research-review-lead/scripts/opencli_transport.py",
            "required script does not exist: skills/research-review-lead/scripts/minimal_bridge.py",
            "required minimal bridge test does not exist: scripts/test_minimal_review_bridge.py",
            *(
                f"required asset does not exist: assets/{name}"
                for name in sorted(CHECKER_MODULE.REQUIRED_ASSETS)
            ),
            *(
                f"SKILL.md does not reference required asset: assets/{name}"
                for name in sorted(CHECKER_MODULE.REQUIRED_ASSETS)
            ),
            *(
                f"expected one authoritative {name}, found 0: "
                for name in CHECKER_MODULE.REQUIRED_ASSETS
            ),
        ]
        self.assertEqual(exit_code, 1)
        self.assertEqual(
            stdout.getvalue().splitlines(),
            ["Skill package checks failed:", *(f"- {error}" for error in expected_errors)],
        )


if __name__ == "__main__":
    unittest.main()
