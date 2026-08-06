"""Regression tests for package-checker execution integrity."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


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


if __name__ == "__main__":
    unittest.main()
