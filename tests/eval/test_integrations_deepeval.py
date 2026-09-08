"""Tests for `runa.eval.integrations.deepeval`: the DeepEval adapter."""

import asyncio
from typing import Any

import pytest
from deepeval.test_case import LLMTestCase

from runa.eval.case import Case
from runa.eval.evaluation.core import Status
from runa.eval.integrations.deepeval import build_test_case, judge_model, run_metric
from runa.eval.tracing.adapter import AgentRun, ToolCallRecord

_STUB_TEST_CASE = LLMTestCase(input="hi", actual_output="ok")


def test_build_test_case_maps_case_and_run_fields() -> None:
    """`build_test_case` carries input/output/expected/context/tools straight across."""
    case = Case(
        input="Cancel order 123",
        expected="Order 123 is cancelled",
        expected_tool="cancel_order",
        context=["policy: refunds within 30 days"],
    )
    run = AgentRun(
        input=case.input,
        final_output="Order 123 has been cancelled.",
        tool_calls=[
            ToolCallRecord(name="cancel_order", arguments='{"order_id": "123"}', output="ok")
        ],
    )

    test_case = build_test_case(case, run)

    assert test_case.input == "Cancel order 123"
    assert test_case.actual_output == "Order 123 has been cancelled."
    assert test_case.expected_output == "Order 123 is cancelled"
    assert test_case.retrieval_context == ["policy: refunds within 30 days"]
    assert test_case.tools_called is not None
    assert test_case.tools_called[0].name == "cancel_order"
    assert test_case.tools_called[0].input_parameters == {"order_id": "123"}
    assert test_case.expected_tools is not None
    assert test_case.expected_tools[0].name == "cancel_order"


def test_build_test_case_tolerates_malformed_tool_arguments() -> None:
    """A tool call whose arguments aren't valid JSON maps to an empty parameter dict."""
    case = Case(input="hi")
    run = AgentRun(
        input="hi",
        final_output="ok",
        tool_calls=[ToolCallRecord(name="search", arguments="not json")],
    )

    test_case = build_test_case(case, run)

    assert test_case.tools_called is not None
    assert test_case.tools_called[0].input_parameters == {}


def test_build_test_case_leaves_expected_tools_none_without_an_expected_tool() -> None:
    """No `expected_tool` on the case means no `expected_tools` on the test case."""
    test_case = build_test_case(Case(input="hi"), AgentRun(input="hi", final_output="ok"))

    assert test_case.expected_tools is None


class _FakeMetric:
    def __init__(self, *, score: float, success: bool, reason: str) -> None:
        self._score = score
        self._success = success
        self.reason = reason

    async def a_measure(self, test_case: Any) -> float:
        return self._score

    def is_successful(self) -> bool:
        return self._success


class _RaisingMetric:
    reason: str | None = None

    async def a_measure(self, test_case: Any) -> float:
        raise RuntimeError("judge call failed")

    def is_successful(self) -> bool:
        raise AssertionError("should not be reached")


def test_run_metric_normalizes_a_passing_verdict() -> None:
    """A metric that measures successfully maps to `PASS` with its score and reason."""
    metric = _FakeMetric(score=0.95, success=True, reason="matches the reference")

    result = asyncio.run(run_metric("answer_correctness", metric, test_case=_STUB_TEST_CASE))

    assert result.status == Status.PASS
    assert result.score == 0.95
    assert result.reason == "matches the reference"


def test_run_metric_normalizes_a_failing_verdict() -> None:
    """A metric that measures below its threshold maps to `FAIL`, not an exception."""
    metric = _FakeMetric(score=0.4, success=False, reason="missing key claim")

    result = asyncio.run(run_metric("answer_correctness", metric, test_case=_STUB_TEST_CASE))

    assert result.status == Status.FAIL


def test_run_metric_maps_an_exception_to_error_not_a_score() -> None:
    """A raised exception (the judge model call failing) becomes `ERROR`, never PASS/FAIL."""
    result = asyncio.run(
        run_metric("answer_correctness", _RaisingMetric(), test_case=_STUB_TEST_CASE)
    )

    assert result.status == Status.ERROR
    assert result.score is None
    assert "judge call failed" in result.reason


def test_judge_model_generates_through_the_named_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """`judge_model(...)`'s `a_generate` runs the prompt through an SDK Agent using that model."""
    captured: dict[str, Any] = {}

    async def fake_run(agent: Any, input: Any, **kwargs: Any) -> Any:
        captured["model"] = agent.model
        captured["input"] = input

        class _Result:
            final_output = "PASS"

        return _Result()

    monkeypatch.setattr("runa.eval.integrations.deepeval.Runner.run", staticmethod(fake_run))

    output = asyncio.run(judge_model("gpt-5.4-nano").a_generate("grade this"))

    assert output == "PASS"
    assert captured["model"] == "gpt-5.4-nano"
    assert captured["input"] == "grade this"
