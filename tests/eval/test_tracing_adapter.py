"""Tests for `runa.eval.tracing.adapter`: `run_agent_for_eval`."""

import asyncio
from typing import Any

import pytest

from runa._runner import RunResult
from runa._types import RunContextWrapper, Usage
from runa.agent import Agent
from runa.eval.case import Case
from runa.eval.tracing.adapter import run_agent_for_eval
from runa.exceptions import MaxTurnsExceeded, RunErrorDetails
from runa.tracing import Span, Trace


class _TestAgent(Agent):
    """A minimal `Agent` for `run_agent_for_eval` to run."""

    name = "UnderTest"


_AGENT = _TestAgent()


def _result(final_output: Any, trace: Trace) -> RunResult:
    return RunResult(
        final_output=final_output,
        context_wrapper=RunContextWrapper(context=None),
        trace=trace,
        _original_input=[],
        _generated_items=[],
    )


def test_run_agent_for_eval_captures_final_output(monkeypatch: pytest.MonkeyPatch) -> None:
    """A successful run's `final_output` and latency are captured, with no error."""
    trace = Trace(id="t1", name="UnderTest", start_time=0.0, end_time=0.0, spans=[])

    async def fake_run(agent: Any, input: Any, **kwargs: Any) -> RunResult:
        return _result("the answer", trace)

    monkeypatch.setattr("runa.eval.tracing.adapter.Runner.run", staticmethod(fake_run))

    run = asyncio.run(run_agent_for_eval(_AGENT, Case(input="hi")))

    assert run.final_output == "the answer"
    assert run.error is None
    assert run.latency >= 0.0


def test_run_agent_for_eval_pairs_tool_calls_with_their_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A `"tool"` span in `RunResult.trace` becomes a `ToolCallRecord`, read straight off it."""
    tool_span = Span(
        id="s1",
        trace_id="t1",
        parent_id=None,
        name="cancel_order",
        type="tool",
        start_time=0.0,
        end_time=0.0,
        input='{"order_id": "123"}',
        output="cancelled",
    )
    trace = Trace(id="t1", name="UnderTest", start_time=0.0, end_time=0.0, spans=[tool_span])

    async def fake_run(agent: Any, input: Any, **kwargs: Any) -> RunResult:
        return _result("done", trace)

    monkeypatch.setattr("runa.eval.tracing.adapter.Runner.run", staticmethod(fake_run))

    run = asyncio.run(run_agent_for_eval(_AGENT, Case(input="cancel order 123")))

    assert len(run.tool_calls) == 1
    assert run.tool_calls[0].name == "cancel_order"
    assert run.tool_calls[0].output == "cancelled"
    assert any(span.type == "tool" for span in run.trace.spans)


def test_run_agent_for_eval_captures_a_run_exception_as_an_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A run that raises a `RunaError` (guardrail tripwire, `MaxTurnsExceeded`, ...) is captured."""

    async def fake_run(agent: Any, input: Any, **kwargs: Any) -> RunResult:
        exc = MaxTurnsExceeded("too many turns")
        exc.run_data = RunErrorDetails(
            input="hi",
            new_items=[],
            raw_responses=[],
            last_agent=_AGENT,
            context_wrapper=RunContextWrapper(context=None, usage=Usage()),
            input_guardrail_results=[],
            output_guardrail_results=[],
        )
        raise exc

    monkeypatch.setattr("runa.eval.tracing.adapter.Runner.run", staticmethod(fake_run))

    run = asyncio.run(run_agent_for_eval(_AGENT, Case(input="hi")))

    assert run.final_output is None
    assert run.error is not None and "too many turns" in run.error
