"""Tests for the built-in `RunHooks`/`AgentHooks` implementations."""

import asyncio
import logging
import re

import pytest
from agents import AgentHooks, RunContextWrapper, RunHooks
from agents.items import ModelResponse
from agents.run_context import AgentHookContext
from agents.usage import Usage

from runa import (
    Agent,
    AuditRunHooks,
    CompositeAgentHooks,
    CompositeRunHooks,
    LoggingAgentHooks,
    LoggingRunHooks,
    MetricsRunHooks,
    TracingRunHooks,
)
from runa.tool import tool as tool_decorator


class Researcher(Agent):
    """An agent used across tests."""

    name = "Researcher"
    instructions = "You research topics."


class Translator(Agent):
    """Another agent used across tests."""

    name = "Translator"
    instructions = "You translate text."


@tool_decorator
def search(query: str) -> str:
    """Search for `query`."""
    return query


_response = ModelResponse(
    output=[],
    usage=Usage(requests=1, input_tokens=10, output_tokens=5, total_tokens=15),
    response_id=None,
)


async def _run_all_run_hooks(hooks: RunHooks[None]) -> None:
    context: RunContextWrapper[None] = RunContextWrapper(context=None)
    agent_context: AgentHookContext[None] = AgentHookContext(context=None)
    researcher, translator = Researcher(), Translator()

    await hooks.on_agent_start(agent_context, researcher)
    await hooks.on_agent_end(agent_context, researcher, "final output")
    await hooks.on_handoff(context, researcher, translator)
    await hooks.on_tool_start(context, researcher, search)
    await hooks.on_tool_end(context, researcher, search, "tool result")
    await hooks.on_llm_start(context, researcher, "system prompt", [])
    await hooks.on_llm_end(context, researcher, _response)


async def _run_all_agent_hooks(hooks: AgentHooks[None]) -> None:
    context: RunContextWrapper[None] = RunContextWrapper(context=None)
    agent_context: AgentHookContext[None] = AgentHookContext(context=None)
    researcher, translator = Researcher(), Translator()

    await hooks.on_start(agent_context, researcher)
    await hooks.on_end(agent_context, researcher, "final output")
    await hooks.on_handoff(context, researcher, translator)
    await hooks.on_tool_start(context, researcher, search)
    await hooks.on_tool_end(context, researcher, search, "tool result")
    await hooks.on_llm_start(context, researcher, "system prompt", [])
    await hooks.on_llm_end(context, researcher, _response)


def test_run_hooks_log_every_callback(caplog: pytest.LogCaptureFixture) -> None:
    """Each `LoggingRunHooks` callback logs a message naming the agent(s) and payload involved."""
    with caplog.at_level(logging.DEBUG, logger="runa"):
        asyncio.run(_run_all_run_hooks(LoggingRunHooks()))

    messages = [r.getMessage() for r in caplog.records]
    assert messages == [
        "agent start: Researcher",
        "agent end: Researcher -> 'final output'",
        "handoff: Researcher -> Translator",
        "tool start: search (Researcher)",
        "tool end: search -> 'tool result'",
        "llm start: Researcher",
        "llm end: Researcher",
    ]


def test_metrics_run_hooks_count_every_callback() -> None:
    """`MetricsRunHooks` counts each callback and accumulates token usage from `on_llm_end`."""
    hooks = MetricsRunHooks()
    asyncio.run(_run_all_run_hooks(hooks))

    assert hooks.agent_starts == 1
    assert hooks.agent_ends == 1
    assert hooks.handoffs == 1
    assert hooks.tool_starts == 1
    assert hooks.tool_ends == 1
    assert hooks.llm_starts == 1
    assert hooks.llm_ends == 1
    assert hooks.usage.requests == 1
    assert hooks.usage.input_tokens == 10
    assert hooks.usage.output_tokens == 5
    assert hooks.usage.total_tokens == 15


def test_tracing_run_hooks_log_every_callback_with_elapsed_time(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Each `TracingRunHooks` `on_*_end` callback logs the elapsed time since its start."""
    with caplog.at_level(logging.DEBUG, logger="runa"):
        asyncio.run(_run_all_run_hooks(TracingRunHooks()))

    messages = [r.getMessage() for r in caplog.records]
    assert messages[0] == "agent start: Researcher"
    assert re.fullmatch(r"agent end: Researcher -> 'final output' \(\d+\.\d+ms\)", messages[1])
    assert messages[2] == "handoff: Researcher -> Translator"
    assert messages[3] == "tool start: search (Researcher)"
    assert re.fullmatch(r"tool end: search -> 'tool result' \(\d+\.\d+ms\)", messages[4])
    assert messages[5] == "llm start: Researcher"
    assert re.fullmatch(r"llm end: Researcher \(\d+\.\d+ms\)", messages[6])


def test_audit_run_hooks_record_every_callback() -> None:
    """`AuditRunHooks` records one timestamped `AuditEvent` per callback, in order."""
    hooks = AuditRunHooks()
    asyncio.run(_run_all_run_hooks(hooks))

    assert [e.event for e in hooks.events] == [
        "agent_start",
        "agent_end",
        "handoff",
        "tool_start",
        "tool_end",
        "llm_start",
        "llm_end",
    ]
    assert all(e.timestamp > 0 for e in hooks.events)
    assert hooks.events[1].agent == "Researcher"
    assert hooks.events[1].detail == "'final output'"
    assert hooks.events[2].agent == "Translator"
    assert hooks.events[2].detail == "from Researcher"
    assert hooks.events[4].detail == "search -> 'tool result'"


def test_composite_run_hooks_dispatches_to_every_hook() -> None:
    """`CompositeRunHooks` forwards each callback to every hook it was built from, in order."""
    metrics, audit = MetricsRunHooks(), AuditRunHooks()
    hooks = CompositeRunHooks(metrics, audit)
    asyncio.run(_run_all_run_hooks(hooks))

    assert metrics.agent_starts == 1
    assert metrics.llm_ends == 1
    assert [e.event for e in audit.events] == [
        "agent_start",
        "agent_end",
        "handoff",
        "tool_start",
        "tool_end",
        "llm_start",
        "llm_end",
    ]


def test_agent_hooks_log_every_callback(caplog: pytest.LogCaptureFixture) -> None:
    """Each `LoggingAgentHooks` callback logs a message naming the agent(s) and payload involved."""
    with caplog.at_level(logging.DEBUG, logger="runa"):
        asyncio.run(_run_all_agent_hooks(LoggingAgentHooks()))

    messages = [r.getMessage() for r in caplog.records]
    assert messages == [
        "agent start: Researcher",
        "agent end: Researcher -> 'final output'",
        "handoff: Translator -> Researcher",
        "tool start: search (Researcher)",
        "tool end: search -> 'tool result'",
        "llm start: Researcher",
        "llm end: Researcher",
    ]


def test_composite_agent_hooks_logs_counts_and_records_every_callback(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """`CompositeAgentHooks` logs, counts, and audits every callback from one hook instance."""
    hooks = CompositeAgentHooks()
    with caplog.at_level(logging.DEBUG, logger="runa"):
        asyncio.run(_run_all_agent_hooks(hooks))

    messages = [r.getMessage() for r in caplog.records]
    assert messages == [
        "agent start: Researcher",
        "agent end: Researcher -> 'final output'",
        "handoff: Translator -> Researcher",
        "tool start: search (Researcher)",
        "tool end: search -> 'tool result'",
        "llm start: Researcher",
        "llm end: Researcher",
    ]

    assert hooks.starts == 1
    assert hooks.ends == 1
    assert hooks.handoffs == 1
    assert hooks.tool_starts == 1
    assert hooks.tool_ends == 1
    assert hooks.llm_starts == 1
    assert hooks.llm_ends == 1
    assert hooks.usage.requests == 1
    assert hooks.usage.input_tokens == 10
    assert hooks.usage.output_tokens == 5
    assert hooks.usage.total_tokens == 15

    assert [e.event for e in hooks.events] == [
        "start",
        "end",
        "handoff",
        "tool_start",
        "tool_end",
        "llm_start",
        "llm_end",
    ]
    assert hooks.events[2].agent == "Researcher"
    assert hooks.events[2].detail == "from Translator"


def test_agent_hooks_can_be_set_on_an_agent_class() -> None:
    """`hooks` is a plain `Agent` field, so `LoggingAgentHooks` can be assigned to it."""

    class Editor(Agent):
        name = "Editor"
        instructions = "You edit text."
        hooks = LoggingAgentHooks()

    assert isinstance(Editor().hooks, LoggingAgentHooks)
