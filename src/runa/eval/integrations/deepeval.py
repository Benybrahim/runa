"""eval/integrations/deepeval.py: the one place DeepEval is imported.

`judge_model()` wraps a bare SDK `Agent` over the same `LitellmProvider`
every `runa.Agent` uses (see `runa.agent`), so DeepEval's metrics grade with
whatever model an app already talks to instead of requiring a separate
client or API key. `build_test_case()`/`run_metric()` translate between
Runa's `Case`/`AgentRun` and DeepEval's `LLMTestCase`/`BaseMetric`, so
`eval/evaluation/semantic.py` never has to import DeepEval itself.
"""

import asyncio
import json
from typing import Any, Protocol, cast

from agents import Agent as BaseAgent
from agents import Runner
from deepeval.models.base_model import DeepEvalBaseLLM
from deepeval.test_case import LLMTestCase, ToolCall

from runa.agent import _RUN_CONFIG
from runa.eval.case import Case
from runa.eval.evaluation.core import EvaluationResult, Status
from runa.eval.tracing.adapter import AgentRun


class Metric(Protocol):
    """The shape `run_metric` needs from a DeepEval metric: enough to grade and report.

    A real `deepeval.metrics.BaseMetric` satisfies this structurally, with no explicit
    inheritance needed; so does a lightweight stand-in built for testing eval cases themselves.
    """

    @property
    def reason(self) -> str | None:
        """A human-readable explanation of the verdict, once graded."""
        ...

    async def a_measure(self, test_case: LLMTestCase) -> float:
        """Grade `test_case`, returning its score (also stored on `self.score`)."""
        ...

    def is_successful(self) -> bool | None:
        """Whether the last `a_measure()` call's score met this metric's threshold."""
        ...


class _RunaJudgeModel(DeepEvalBaseLLM):
    """Adapts a Runa-reachable model to DeepEval's `DeepEvalBaseLLM` interface."""

    def __init__(self, model: str) -> None:
        """Grade through `model`, run via the SDK's `Runner` like any other Runa agent call."""
        self._model_name = model
        super().__init__(model)

    def load_model(self) -> _RunaJudgeModel:
        """No separate client to load: the model is resolved per-call by `Runner.run`."""
        return self

    def get_model_name(self) -> str:
        """Return the model name DeepEval reports in its own logs/costs."""
        return self._model_name

    async def a_generate(self, prompt: str) -> str:
        """Send `prompt` to `model` through a bare, tool-less SDK `Agent`."""
        judge_agent = BaseAgent(name="Judge", model=self._model_name, tools=[])
        result = await Runner.run(judge_agent, prompt, run_config=_RUN_CONFIG)
        return result.final_output

    def generate(self, prompt: str) -> str:
        """Sync fallback for the rare DeepEval code path that doesn't await `a_generate`."""
        return asyncio.run(self.a_generate(prompt))


def judge_model(model: str) -> DeepEvalBaseLLM:
    """Build the judge DeepEval's metrics should grade with."""
    return _RunaJudgeModel(model)


def _parsed_arguments(arguments: str) -> dict[str, object]:
    try:
        parsed = json.loads(arguments)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def build_test_case(case: Case, run: AgentRun) -> LLMTestCase:
    """Translate a `Case`/`AgentRun` pair into the `LLMTestCase` DeepEval's metrics grade."""
    return LLMTestCase(
        input=case.input,
        actual_output=run.final_output or "",
        expected_output=case.expected,
        retrieval_context=cast(Any, case.context),
        tools_called=[
            ToolCall(
                name=tool_call.name,
                input_parameters=_parsed_arguments(tool_call.arguments),
                output=tool_call.output,
            )
            for tool_call in run.tool_calls
        ],
        expected_tools=(
            [ToolCall(name=case.expected_tool, input_parameters=None)]
            if case.expected_tool
            else None
        ),
    )


async def run_metric(name: str, metric: Metric, test_case: LLMTestCase) -> EvaluationResult:
    """Grade `test_case` with `metric`, normalizing both its verdict and any failure.

    A raised exception (the judge model call failing, a malformed response) becomes `ERROR`,
    never a `PASS`/`FAIL` score of convenience: see `eval/evaluation/core.py`'s `Status`.
    """
    try:
        score = await metric.a_measure(test_case)
    except Exception as exc:
        return EvaluationResult(metric=name, status=Status.ERROR, reason=str(exc))
    status = Status.PASS if metric.is_successful() else Status.FAIL
    return EvaluationResult(metric=name, status=status, reason=metric.reason or "", score=score)
