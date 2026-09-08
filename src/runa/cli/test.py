"""cli/test.py: `runa test`, run app/tests/ test functions.

Complements `runa eval` (cli/eval.py): tests verify invariants with plain
`assert` statements against a result, evals measure behavior with
`expect(result).to_...()`. Import every `app/tests/` module and run its
`test_*` functions, catching `AssertionError` instead of crashing so a full
report comes back in one pass.

Deliberately not a pytest wrapper: `runa` doesn't add pytest as a runtime
dependency just so a generated app can run its own tests, matching
`run_evals()`'s choice not to depend on an external harness either.
"""

import asyncio
import importlib
import inspect
from dataclasses import dataclass
from pathlib import Path

from runa.cli._project import NotARunaProject, loaded_app


@dataclass
class TestResult:
    """The outcome of running one `test_*` function."""

    name: str
    passed: bool
    error: str | None = None


def run_project_tests(root: Path) -> list[TestResult]:
    """Import every `app/tests/` module and run its `test_*` functions."""
    tests_dir = root / "app" / "tests"
    if not tests_dir.is_dir():
        raise NotARunaProject(
            f"{tests_dir} does not exist, run this from inside a Runa "
            "project created with `runa new`"
        )

    with loaded_app(root):
        results: list[TestResult] = []
        for test_file in sorted(tests_dir.glob("*.py")):
            if test_file.stem == "__init__":
                continue
            module = importlib.import_module(f"app.tests.{test_file.stem}")
            for attr_name, attr in inspect.getmembers(module, inspect.isfunction):
                if not attr_name.startswith("test_"):
                    continue
                name = f"{test_file.stem}.{attr_name}"
                try:
                    outcome = attr()
                    if inspect.isawaitable(outcome):
                        asyncio.run(outcome)
                except AssertionError as exc:
                    results.append(TestResult(name=name, passed=False, error=str(exc)))
                else:
                    results.append(TestResult(name=name, passed=True))
        return results
