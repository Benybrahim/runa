import pytest

from runa.cli.new import scaffold_project
from runa.cli.test import NotARunaProject, run_project_tests

_TEST_MODULE = """
from runa import Agent


class EchoAgent(Agent):
    instructions = "Echo pleasantly."


def test_completes_with_hi():
    run = EchoAgent.run("hello")
    assert run.result == "hi"


def test_wrong_expectation():
    run = EchoAgent.run("hello")
    assert run.result == "goodbye"
"""

_NOT_A_TEST_MODULE = "def helper():\n    return 1\n"


def _scaffold_with_tests(tmp_path, test_source: str, *, responses: int):
    project_dir = scaffold_project("acme", root=tmp_path)
    scripted = ", ".join(['Message(role=Role.ASSISTANT, content="hi")'] * responses)
    (project_dir / "main.py").write_text(
        "from runa import configure\n"
        "from tests.fakes import FakeProvider\n"
        "from runa.core import Message, Role\n\n"
        f"configure(provider=FakeProvider(responses=[{scripted}]))\n"
    )
    (project_dir / "app" / "tests" / "echo_test.py").write_text(test_source)
    return project_dir


def test_run_project_tests_reports_pass_and_fail(tmp_path):
    # each test_* function drives its own Run, so one scripted response is
    # needed per function collected; alphabetical order matches definition
    # order here (completes_with_hi, then wrong_expectation).
    project_dir = _scaffold_with_tests(tmp_path, _TEST_MODULE, responses=2)

    results = run_project_tests(project_dir)

    names = {result.name: result.passed for result in results}
    assert names == {
        "echo_test.test_completes_with_hi": True,
        "echo_test.test_wrong_expectation": False,
    }


def test_run_project_tests_ignores_non_test_functions(tmp_path):
    project_dir = _scaffold_with_tests(tmp_path, _NOT_A_TEST_MODULE, responses=0)

    results = run_project_tests(project_dir)

    assert results == []


def test_run_project_tests_raises_outside_a_runa_project(tmp_path):
    with pytest.raises(NotARunaProject):
        run_project_tests(tmp_path)
