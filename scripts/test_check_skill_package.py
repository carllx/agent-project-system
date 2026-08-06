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


class PackageCheckerExecutionTests(unittest.TestCase):
    def run_fake_test_file(
        self, source: str, *, timeout_seconds: float = 5
    ) -> tuple[int, list[str]]:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fake_transport_tests.py"
            path.write_text(source, encoding="utf-8")
            return CHECKER_MODULE.run_transport_tests(
                path, timeout_seconds=timeout_seconds
            )

    def test_names_in_a_tuple_do_not_count_as_tests(self) -> None:
        count, errors = self.run_fake_test_file(
            "SCENARIOS = ('test_delivery', 'test_recovery', 'test_deduplication')\n"
        )
        self.assertEqual(count, 0)
        self.assertEqual(
            errors, ["transport test execution discovered zero test functions"]
        )

    def test_zero_test_functions_cannot_pass(self) -> None:
        count, errors = self.run_fake_test_file("VALUE = 1\n")
        self.assertEqual(count, 0)
        self.assertEqual(
            errors, ["transport test execution discovered zero test functions"]
        )

    def test_forged_pass_without_execution_cannot_pass(self) -> None:
        count, errors = self.run_fake_test_file(
            "def test_never_executed():\n"
            "    raise AssertionError('must fail if called')\n"
            "\n"
            "if __name__ == '__main__':\n"
            "    print('PASS: test_never_executed')\n"
        )
        self.assertEqual(count, 1)
        self.assertTrue(any("exit code 1" in error for error in errors))

    def test_real_test_exception_cannot_pass(self) -> None:
        count, errors = self.run_fake_test_file(
            "def test_failure():\n"
            "    raise RuntimeError('real failure')\n"
        )
        self.assertEqual(count, 1)
        self.assertTrue(any("exit code 1" in error for error in errors))

    def test_timeout_cannot_pass(self) -> None:
        count, errors = self.run_fake_test_file(
            "import time\n"
            "def test_too_slow():\n"
            "    time.sleep(1)\n",
            timeout_seconds=0.05,
        )
        self.assertEqual(count, 1)
        self.assertEqual(
            errors, ["transport test execution timed out after 0.05 seconds"]
        )

    def test_multiple_tests_are_each_called_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fake_transport_tests.py"
            calls = Path(directory) / "calls.txt"
            path.write_text(
                "from pathlib import Path\n"
                f"CALLS = Path({str(calls)!r})\n"
                "def record(name):\n"
                "    with CALLS.open('a', encoding='utf-8') as stream:\n"
                "        stream.write(name + '\\n')\n"
                "def test_one():\n"
                "    record('test_one')\n"
                "def test_two():\n"
                "    record('test_two')\n",
                encoding="utf-8",
            )
            count, errors = CHECKER_MODULE.run_transport_tests(path)
            self.assertEqual(count, 2)
            self.assertEqual(errors, [])
            self.assertEqual(
                calls.read_text(encoding="utf-8").splitlines(),
                ["test_one", "test_two"],
            )

    def test_async_test_is_explicitly_rejected(self) -> None:
        count, errors = self.run_fake_test_file(
            "async def test_async_case():\n"
            "    return None\n"
        )
        self.assertEqual(count, 1)
        self.assertEqual(
            errors, ["unsupported async transport tests: test_async_case"]
        )

    def test_import_failure_cannot_pass(self) -> None:
        count, errors = self.run_fake_test_file(
            "raise RuntimeError('import failed')\n"
            "def test_never_imported():\n"
            "    return None\n"
        )
        self.assertEqual(count, 1)
        self.assertTrue(any("exit code 1" in error for error in errors))

    def test_missing_runner_result_cannot_pass(self) -> None:
        count, errors = self.run_fake_test_file(
            "import os\n"
            "def test_exits_before_result():\n"
            "    os._exit(0)\n"
        )
        self.assertEqual(count, 1)
        self.assertEqual(
            errors, ["transport test runner produced no completion result"]
        )

    def test_main_success_output_is_preserved(self) -> None:
        stdout = io.StringIO()
        with mock.patch.object(
            CHECKER_MODULE, "run_transport_tests", return_value=(101, [])
        ), contextlib.redirect_stdout(stdout):
            exit_code = CHECKER_MODULE.main()

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            stdout.getvalue(),
            "Skill package checks passed: skills/research-review-lead\n"
            "Entry: one valid SKILL.md with matching name and description.\n"
            "Version: 0.4.11 (simple SemVer).\n"
            "Assets: five required files, each with one authoritative copy.\n"
            "Transport structure: wrapper and experiment protocol module syntax and "
            "required package markers validated.\n"
            "Transport tests: executed 101 discovered pure-local tests; the controlled "
            "runner called every test exactly once without exceptions.\n"
            "Loop contract: roles, Goal Contract, delivery state, conversation identity, "
            "and HITL markers exist.\n"
            "Portability: referenced resources exist; no forbidden runtime dependencies "
            "found.\n",
        )

    def test_main_failure_exit_code_is_preserved(self) -> None:
        stdout = io.StringIO()
        with mock.patch.object(
            CHECKER_MODULE,
            "check_package_layout",
            return_value=["synthetic package failure"],
        ), mock.patch.object(
            CHECKER_MODULE, "run_transport_tests", return_value=(101, [])
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
                "EXPERIMENT_PROTOCOL_SCRIPT": (
                    package / "scripts" / "experiment_protocol.py"
                ),
                "TRANSPORT_TEST": root / "scripts" / "test_opencli_transport.py",
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
            "required transport wrapper does not exist: scripts/opencli_transport.py",
            "required experiment protocol module does not exist: "
            "scripts/experiment_protocol.py",
            "required pure-local transport test does not exist: "
            "scripts/test_opencli_transport.py",
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

    def test_transport_runner_is_invoked_once(self) -> None:
        stdout = io.StringIO()
        with mock.patch.object(
            CHECKER_MODULE, "run_transport_tests", return_value=(101, [])
        ) as runner, contextlib.redirect_stdout(stdout):
            exit_code = CHECKER_MODULE.main()

        self.assertEqual(exit_code, 0)
        runner.assert_called_once_with(CHECKER_MODULE.TRANSPORT_TEST)

    def test_transport_failure_reaches_main_exit_code(self) -> None:
        stdout = io.StringIO()
        failure = "transport test execution failed with exit code 1: sentinel"
        with mock.patch.object(
            CHECKER_MODULE, "run_transport_tests", return_value=(101, [failure])
        ) as runner, contextlib.redirect_stdout(stdout):
            exit_code = CHECKER_MODULE.main()

        self.assertEqual(exit_code, 1)
        runner.assert_called_once_with(CHECKER_MODULE.TRANSPORT_TEST)
        self.assertIn(f"- {failure}\n", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
