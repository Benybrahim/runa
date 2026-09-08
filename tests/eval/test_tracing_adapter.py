"""Tests for `runa.eval.tracing.adapter`: `run_agent_for_eval`."""

import asyncio
from typing import Any

import pytest
from openai.types.responses import ResponseFunctionToolCall

from runa.agent import Agent
from runa.eval.case import Case
from runa.eval.tracing.adapter import run_agent_for_eval


class _TestAgent(Agent):
    """A minimal `Agent` for `run_agent_for_eval` to run."""

    name = "UnderTest"


_AGENT = _TestAgent()


def _tool_call_item(name: str, call_id: str, arguments: str = "{}") -> Any:
    from agents.items import ToolCallItem

    raw = ResponseFunctionToolCall(
        call_id=call_id, name=name, arguments=arguments, type="function_call"
    )
    return ToolCallItem(agent=_AGENT, raw_item=raw)


def _tool_call_output_item(call_id: str, output: str) -> Any:
    from agents.items import ToolCallOutputItem

    raw = {"call_id": call_id, "output": output, "type": "function_call_output"}
    return ToolCallOutputItem(agent=_AGENT, raw_item=raw, output=output)


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
    """A `ToolCallItem` is paired with the `ToolCallOutputItem` sharing its `call_id`."""

    class _FakeResult:
        final_output = "done"
        new_items = [
            _tool_call_item("cancel_order", "call_1", arguments='{"order_id": "123"}'),
            _tool_call_output_item("call_1", "cancelled"),
        ]

    async def fake_run(agent: Any, input: Any, **kwargs: Any) -> Any:
        return _FakeResult()

    monkeypatch.setattr("runa.eval.tracing.adapter.Runner.run", staticmethod(fake_run))

    run = asyncio.run(run_agent_for_eval(_AGENT, Case(input="cancel order 123")))

    assert len(run.tool_calls) == 1
    assert run.tool_calls[0].name == "cancel_order"
    assert run.tool_calls[0].output == "cancelled"


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
