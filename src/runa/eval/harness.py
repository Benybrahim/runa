"""eval/harness.py: run agents against cases and assert on the resulting Run.

An eval case exercises the same `Agent`/`Executor`/`Run` code path as
production (manifesto §8); `run_evals()` is a thin loop around
`executor.run()`, not a parallel mock harness. `expect(run).to_...()` reads
the same `Run` a test would, so eval assertions and application invariants
share one vocabulary.

`Expectation` holds both halves of manifesto §12. `to_be_completed`,
`to_have_result`, `to_contain`, and `to_have_called` verify invariants:
deterministic facts about the Run's shape, cheap enough for `test`-style
checks. `to_satisfy` and its named rubrics (`to_be_helpful`, `to_be_factual`,
`not_to_hallucinate`, `to_meet_the_goal`, see `eval/judge.py`) measure
behavior: a real, non-deterministic model call grading what the agent
actually did.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from runa.agent import Agent
from runa.application import application
from runa.core import Run, RunStatus
from runa.eval.judge import (
    RUBRIC_FACTUAL,
    RUBRIC_GOAL,
    RUBRIC_HELPFUL,
    RUBRIC_NOT_HALLUCINATE,
    Judge,
)
from runa.runtime import Executor


class ExpectationFailed(AssertionError):
    """Raised when an expect(...) assertion fails."""


class Expectation:
    def __init__(self, run: Run) -> None:
        self.run = run

    def to_be_completed(self) -> "Expectation":
        if self.run.status != RunStatus.COMPLETED:
            detail = f": {self.run.error}" if self.run.error else ""
            raise ExpectationFailed(
                f"expected run to be completed, got {self.run.status}{detail}"
            )
        return self

    def to_be_failed(self) -> "Expectation":
        if self.run.status != RunStatus.FAILED:
            raise ExpectationFailed(f"expected run to be failed, got {self.run.status}")
        return self

    def to_have_error(self, text: str) -> "Expectation":
        if self.run.error is None or text not in self.run.error:
            raise ExpectationFailed(
                f"expected run.error to contain {text!r}, got {self.run.error!r}"
            )
        return self

    def to_have_result(self, expected: Any) -> "Expectation":
        if self.run.result != expected:
            raise ExpectationFailed(
                f"expected result {expected!r}, got {self.run.result!r}"
            )
        return self

    def to_contain(self, text: str) -> "Expectation":
        if not any(text in str(message.content) for message in self.run.messages):
            raise ExpectationFailed(f"expected a message containing {text!r}")
        return self

    def to_have_called(self, tool_name: str) -> "Expectation":
        if not any(call.name == tool_name for call in self.run.tool_calls):
            raise ExpectationFailed(f"expected tool {tool_name!r} to have been called")
        return self

    def to_satisfy(self, rubric: str, *, judge: Judge | None = None) -> "Expectation":
        """Grade this Run against `rubric` with an LLM judge (manifesto §12).

        Unlike the structural checks above, this makes a real model request
        and its result is not deterministic; reserve it for
        `app/evaluations/` cases, not `test`-style invariants. Defaults to a
        `Judge` backed by `runa.configure()`'s default Provider; pass `judge`
        explicitly to grade with a different model, or a `FakeProvider` in
        tests of your own eval cases.
        """
        judge = judge or Judge(application.provider)
        verdict = judge.grade(self.run, rubric)
        if not verdict.passed:
            raise ExpectationFailed(
                f"failed to satisfy {rubric!r}: {verdict.reasoning}"
            )
        return self

    def to_be_helpful(self, *, judge: Judge | None = None) -> "Expectation":
        return self.to_satisfy(RUBRIC_HELPFUL, judge=judge)

    def to_be_factual(self, *, judge: Judge | None = None) -> "Expectation":
        return self.to_satisfy(RUBRIC_FACTUAL, judge=judge)

    def not_to_hallucinate(self, *, judge: Judge | None = None) -> "Expectation":
        return self.to_satisfy(RUBRIC_NOT_HALLUCINATE, judge=judge)

    def to_meet_the_goal(self, *, judge: Judge | None = None) -> "Expectation":
        return self.to_satisfy(RUBRIC_GOAL, judge=judge)


def expect(run: Run) -> Expectation:
    return Expectation(run)


@dataclass
class EvalCase:
    name: str
    input: Any
    check: Callable[[Run], Any]


@dataclass
class EvalResult:
    case: EvalCase
    run: Run
    passed: bool
    error: str | None = None


def run_evals(
    agent: Agent, executor: Executor, cases: list[EvalCase]
) -> list[EvalResult]:
    """Run every case's input through `agent`/`executor` and check it.

    Every case runs to completion even if an earlier one fails, so a full
    eval report comes back in one pass.
    """
    results = []
    for eval_case in cases:
        run = executor.run(agent, Run(input=eval_case.input))
        try:
            eval_case.check(run)
        except ExpectationFailed as exc:
            results.append(
                EvalResult(case=eval_case, run=run, passed=False, error=str(exc))
            )
        else:
            results.append(EvalResult(case=eval_case, run=run, passed=True))
    return results
