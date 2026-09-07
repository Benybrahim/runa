"""Tests for the built-in `RunHooks`/`AgentHooks` implementations."""

import asyncio
import logging

import pytest
from agents import RunContextWrapper
from agents.items import ModelResponse
from agents.run_context import AgentHookContext
from agents.usage import Usage

from runa import Agent, LoggingAgentHooks, LoggingRunHooks
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


_response = ModelResponse(output=[], usage=Usage(), response_id=None)


async def _run_all_run_hooks(hooks: LoggingRunHooks) -> None:
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


async def _run_all_agent_hooks(hooks: LoggingAgentHooks) -> None:
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


def test_agent_hooks_can_be_set_on_an_agent_class() -> None:
    """`hooks` is a plain `Agent` field, so `LoggingAgentHooks` can be assigned to it."""

    class Editor(Agent):
        name = "Editor"
        instructions = "You edit text."
        hooks = LoggingAgentHooks()

    assert isinstance(Editor().hooks, LoggingAgentHooks)
