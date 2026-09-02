"""eval/harness.py: run agents against cases and assert on the resulting Run.

An eval case exercises the same `Agent`/`Executor`/`Run` code path as
production (manifesto §8) — `run_evals()` is a thin loop around
`executor.run()`, not a parallel mock harness. `expect(run).to_...()` reads
the same `Run` a test would, so eval assertions and application invariants
share one vocabulary.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from runa.agent import Agent
from runa.core import Run, RunStatus
from runa.runtime import Executor


class ExpectationFailed(AssertionError):
    """Raised when an expect(...) assertion fails."""


class Expectation:
    def __init__(self, run: Run) -> None:
        self.run = run

    def to_be_completed(self) -> "Expectation":
        if self.run.status != RunStatus.COMPLETED:
            raise ExpectationFailed(
                f"expected run to be completed, got {self.run.status}"
            )
        return self

    def to_be_failed(self) -> "Expectation":
        if self.run.status != RunStatus.FAILED:
            raise ExpectationFailed(f"expected run to be failed, got {self.run.status}")
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


def expect(run: Run) -> Expectation:
    return Expectation(run)


@dataclass
class EvalCase:
    name: str
    input: Any
    check: Callable[[Run], None]


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
