import pytest

from runa.cli.eval import InvalidEvalModule, NotARunaProject, run_project_evals
from runa.cli.new import scaffold_project

_MAIN_PY = """
from runa import configure
from tests.fakes import FakeProvider
from runa.core import Message, Role

configure(provider=FakeProvider(responses=[
    Message(role=Role.ASSISTANT, content="hi"),
    Message(role=Role.ASSISTANT, content="hi"),
]))
"""

_EVAL_MODULE = """
from runa import Agent, EvalCase, expect


class EchoAgent(Agent):
    instructions = "Echo pleasantly."


agent = EchoAgent()

cases = [
    EvalCase(
        name="says hi",
        input="hello",
        check=lambda run: expect(run).to_be_completed().to_contain("hi"),
    ),
    EvalCase(
        name="wrong expectation",
        input="hello",
        check=lambda run: expect(run).to_contain("goodbye"),
    ),
]
"""

_INVALID_EVAL_MODULE = "value = 1\n"


def _scaffold_with_evals(tmp_path, eval_source: str):
    project_dir = scaffold_project("acme", root=tmp_path)
    (project_dir / "main.py").write_text(_MAIN_PY)
    (project_dir / "app" / "evaluations" / "echo_eval.py").write_text(eval_source)
    return project_dir


def test_run_project_evals_reports_pass_and_fail(tmp_path):
    project_dir = _scaffold_with_evals(tmp_path, _EVAL_MODULE)

    results = run_project_evals(project_dir)

    assert [result.case.name for result in results] == ["says hi", "wrong expectation"]
    assert results[0].passed is True
    assert results[1].passed is False


def test_run_project_evals_raises_outside_a_runa_project(tmp_path):
    with pytest.raises(NotARunaProject):
        run_project_evals(tmp_path)


def test_run_project_evals_raises_for_a_module_missing_agent_or_cases(tmp_path):
    project_dir = _scaffold_with_evals(tmp_path, _INVALID_EVAL_MODULE)
    (project_dir / "main.py").write_text(
        "from runa import configure\nfrom tests.fakes import FakeProvider\n"
        "configure(provider=FakeProvider(responses=[]))\n"
    )

    with pytest.raises(InvalidEvalModule):
        run_project_evals(project_dir)
