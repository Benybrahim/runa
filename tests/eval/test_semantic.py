"""Tests for `runa.eval.evaluation.semantic`: automatic metric activation."""

import asyncio
from typing import Any

import pytest

from runa.eval.case import Case
from runa.eval.evaluation.core import EvaluationResult, Status
from runa.eval.evaluation.defaults import DEFAULT_THRESHOLDS
from runa.eval.evaluation.semantic import evaluate_semantic
from runa.eval.tracing.adapter import AgentRun


def _run_semantic(case: Case, monkeypatch: pytest.MonkeyPatch) -> dict[str, EvaluationResult]:
    calls: dict[str, EvaluationResult] = {}

    async def fake_run_metric(name: str, metric: Any, test_case: Any) -> EvaluationResult:
        result = EvaluationResult(metric=name, status=Status.PASS, reason="stub", score=1.0)
        calls[name] = result
        return result

    monkeypatch.setattr("runa.eval.evaluation.semantic.run_metric", fake_run_metric)

    run = AgentRun(input=case.input, final_output="the answer")
    results = asyncio.run(
        evaluate_semantic(case, run, model="gpt-5.4-nano", thresholds=DEFAULT_THRESHOLDS)
    )
    by_metric = {result.metric: result for result in results}
    assert set(calls) | {
        name for name, result in by_metric.items() if result.status == Status.SKIPPED
    } == set(by_metric)
    return by_metric


def test_task_completion_and_relevance_always_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """With no `expected`, `context`, or `expected_tool`, only the two unconditional metrics run."""
    results = _run_semantic(Case(input="what's the weather?"), monkeypatch)

    assert results["task_completion"].status == Status.PASS
    assert results["answer_relevance"].status == Status.PASS
    assert results["answer_correctness"].status == Status.SKIPPED
    assert results["faithfulness"].status == Status.SKIPPED
    assert results["tool_correctness"].status == Status.SKIPPED


def test_expected_answer_activates_correctness(monkeypatch: pytest.MonkeyPatch) -> None:
    """A case with `expected` activates answer correctness."""
    results = _run_semantic(Case(input="refund policy?", expected="30 days"), monkeypatch)

    assert results["answer_correctness"].status == Status.PASS
    assert results["faithfulness"].status == Status.SKIPPED
    assert results["tool_correctness"].status == Status.SKIPPED


def test_context_activates_faithfulness(monkeypatch: pytest.MonkeyPatch) -> None:
    """A case with `context` (retrieval passages) activates faithfulness."""
    results = _run_semantic(
        Case(input="refund policy?", context=["refunds within 30 days"]), monkeypatch
    )

    assert results["faithfulness"].status == Status.PASS
    assert results["answer_correctness"].status == Status.SKIPPED


def test_expected_tool_activates_tool_correctness(monkeypatch: pytest.MonkeyPatch) -> None:
    """A case with `expected_tool` activates tool correctness."""
    results = _run_semantic(
        Case(input="cancel order 123", expected_tool="cancel_order"), monkeypatch
    )

    assert results["tool_correctness"].status == Status.PASS
    assert results["answer_correctness"].status == Status.SKIPPED
    assert results["faithfulness"].status == Status.SKIPPED
