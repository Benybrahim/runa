"""Tests for `runa.cli.eval`: `run_project_evals`."""

from pathlib import Path
from typing import Any

import pytest

from runa.cli._project import NotARunaProject
from runa.cli.eval import InvalidEvalModule, run_project_evals
from runa.cli.new import scaffold_project


def _write_evaluation(project_dir: Path, filename: str, source: str) -> None:
    (project_dir / "evals" / filename).write_text(source)


def test_run_project_evals_raises_outside_a_runa_project(tmp_path: Path) -> None:
    """`run_project_evals` refuses to run where `evals/` doesn't exist."""
    with pytest.raises(NotARunaProject):
        run_project_evals(tmp_path)


def test_run_project_evals_raises_for_a_module_missing_agent_or_dataset(tmp_path: Path) -> None:
    """A module under `evals/` that doesn't declare `agent`/`dataset` is rejected."""
    project_dir = scaffold_project("demo", root=tmp_path)
    _write_evaluation(project_dir, "broken_eval.py", "agent = None\n")

    with pytest.raises(InvalidEvalModule):
        run_project_evals(project_dir)


def test_run_project_evals_evaluates_every_declared_dataset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every module's `agent`/`dataset` is run through `agent.evaluate()`."""
    project_dir = scaffold_project("demo", root=tmp_path)
    _write_evaluation(
        project_dir,
        "support_eval.py",
        (
            "from runa import Agent, Case\n\n\n"
            "class _Placeholder(Agent):\n"
            "    name = 'Placeholder'\n\n\n"
            "agent = _Placeholder()\n"
            "dataset: list[Case] = [Case(input='hi', expected='hi')]\n"
        ),
    )

    async def fake_run(agent: Any, input: Any, **kwargs: Any) -> Any:
        from dataclasses import dataclass, field

        from runa.tracing import Trace

        @dataclass
        class _FakeResult:
            final_output: Any = input
            new_items: list[Any] = field(default_factory=list)
            trace: Trace = field(
                default_factory=lambda: Trace(id="t", name="t", start_time=0.0, spans=[])
            )

        return _FakeResult()

    async def fake_evaluate_semantic(*args: Any, **kwargs: Any) -> list[Any]:
        return []

    monkeypatch.setattr("runa.eval.tracing.adapter.Runner.run", staticmethod(fake_run))
    monkeypatch.setattr("runa.eval.evaluate.evaluate_semantic", fake_evaluate_semantic)
    monkeypatch.setattr("runa.eval.evaluate.save_report", lambda report: 1)

    reports = run_project_evals(project_dir)

    assert len(reports) == 1
    assert len(reports[0].cases) == 1
    assert reports[0].cases[0].passed
