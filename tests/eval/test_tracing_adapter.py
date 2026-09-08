"""Tests for `runa.eval.tracing.adapter`: `run_agent_for_eval`."""

import asyncio
from typing import Any

import pytest
from agents import tracing as agents_tracing

from runa.agent import Agent
from runa.eval.case import Case
from runa.eval.tracing.adapter import run_agent_for_eval


class _TestAgent(Agent):
    """A minimal `Agent` for `run_agent_for_eval` to run."""

    name = "UnderTest"


_AGENT = _TestAgent()


def test_run_agent_for_eval_captures_final_output(monkeypatch: pytest.MonkeyPatch) -> None:
    """A successful run's `final_output` and latency are captured, with no error."""

    class _FakeResult:
        final_output = "the answer"
        new_items: list[Any] = []

    async def fake_run(agent: Any, input: Any, **kwargs: Any) -> Any:
        return _FakeResult()

    monkeypatch.setattr("runa.eval.tracing.adapter.Runner.run", staticmethod(fake_run))

    run = asyncio.run(run_agent_for_eval(_AGENT, Case(input="hi")))

    assert run.final_output == "the answer"
    assert run.error is None
    assert run.latency >= 0.0


def test_run_agent_for_eval_pairs_tool_calls_with_their_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A tool's `function_span` becomes a `ToolCallRecord`, read from the shared `Trace`.

    `fake_run` opens the same real SDK trace/span primitives `Runner.run()` would, using the
    `trace_id` `run_agent_for_eval`'s `capture_trace` generated (passed in via `run_config`), so
    `RunaTraceProcessor` populates `AgentRun.trace` for real instead of a parallel fake shape.
    """

    class _FakeResult:
        final_output = "done"

    async def fake_run(agent: Any, input: Any, *, run_config: Any, **kwargs: Any) -> Any:
        with (
            agents_tracing.trace(
                run_config.workflow_name,
                trace_id=run_config.trace_id,
                group_id=run_config.group_id,
                metadata=run_config.trace_metadata,
            ),
            agents_tracing.function_span(
                "cancel_order", input='{"order_id": "123"}', output="cancelled"
            ),
        ):
            pass
        return _FakeResult()

    monkeypatch.setattr("runa.eval.tracing.adapter.Runner.run", staticmethod(fake_run))

    run = asyncio.run(run_agent_for_eval(_AGENT, Case(input="cancel order 123")))

    assert len(run.tool_calls) == 1
    assert run.tool_calls[0].name == "cancel_order"
    assert run.tool_calls[0].output == "cancelled"
    assert any(span.type == "tool" for span in run.trace.spans)


def test_run_agent_for_eval_captures_a_run_exception_as_an_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A run that raises an `AgentsException` (trace extraction failure) is captured, not raised."""
    from agents.exceptions import MaxTurnsExceeded

    async def fake_run(agent: Any, input: Any, **kwargs: Any) -> Any:
        raise MaxTurnsExceeded("too many turns")

    monkeypatch.setattr("runa.eval.tracing.adapter.Runner.run", staticmethod(fake_run))

    run = asyncio.run(run_agent_for_eval(_AGENT, Case(input="hi")))

    assert run.final_output is None
    assert run.error is not None and "too many turns" in run.error
