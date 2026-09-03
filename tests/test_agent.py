import asyncio
import time

import pytest

from runa.agent import (
    Agent,
    AsyncDelegateTool,
    DelegateTool,
    DuplicateToolName,
    UnknownApprovalTool,
)
from runa.config import ProviderNotConfigured, configure
from runa.core import Conversation, Message, Role, RunStatus, ToolCall
from runa.runtime import AsyncExecutor, Executor
from runa.tool import Tool
from tests.fakes import FakeAsyncProvider, FakeProvider


class Ledger(Tool):
    def call(self) -> None:
        pass


class Reporting(Tool):
    def call(self) -> None:
        pass


class TransferFunds(Tool):
    def call(self, amount: float) -> None:
        pass


def test_agent_resolves_tool_classes_into_instances():
    class FinanceAgent(Agent):
        tools = [Ledger, Reporting]

    resolved = FinanceAgent.resolved_tools()
    assert set(resolved) == {"Ledger", "Reporting"}
    assert isinstance(resolved["Ledger"], Ledger)


def test_agent_accepts_tool_instances_directly():
    ledger = Ledger()

    class FinanceAgent(Agent):
        tools = [ledger]

    assert FinanceAgent.resolved_tools()["Ledger"] is ledger


def test_duplicate_tool_names_raise_at_class_definition():
    with pytest.raises(DuplicateToolName):

        class BrokenAgent(Agent):
            tools = [Ledger, Ledger]


def test_requires_approval_must_reference_a_declared_tool():
    with pytest.raises(UnknownApprovalTool):

        class BrokenAgent(Agent):
            tools = [Ledger]
            requires_approval = [TransferFunds]


def test_requires_approval_marks_matching_tool_name():
    class FinanceAgent(Agent):
        tools = [Ledger, Reporting, TransferFunds]
        requires_approval = [TransferFunds]

    assert FinanceAgent.approval_tool_names() == {"TransferFunds"}


def test_tool_level_requires_approval_is_respected_without_declaration():
    approval_tool = Ledger()
    approval_tool.requires_approval = True

    class FinanceAgent(Agent):
        tools = [approval_tool]

    assert FinanceAgent.approval_tool_names() == {"Ledger"}


def test_default_hooks_are_noops():
    class SimpleAgent(Agent):
        pass

    agent = SimpleAgent()
    agent.before_run(None)
    agent.plan(None)
    agent.review(None)
    agent.after_run(None)


def test_subclasses_do_not_share_resolved_tool_cache():
    class AgentA(Agent):
        tools = [Ledger]

    class AgentB(Agent):
        tools = [Reporting]

    assert set(AgentA.resolved_tools()) == {"Ledger"}
    assert set(AgentB.resolved_tools()) == {"Reporting"}


def test_run_uses_the_app_default_provider_when_no_executor_is_given():
    class SimpleAgent(Agent):
        pass

    configure(provider=FakeProvider([Message(role=Role.ASSISTANT, content="hi")]))

    run = SimpleAgent.run("hello")

    assert run.status == RunStatus.COMPLETED
    assert run.result == "hi"


def test_run_raises_if_no_default_provider_and_no_executor(monkeypatch):
    monkeypatch.setattr("runa.config._default_provider", None)

    class SimpleAgent(Agent):
        pass

    with pytest.raises(ProviderNotConfigured):
        SimpleAgent.run("hello")


def test_run_accepts_an_explicit_executor_as_an_escape_hatch():
    class SimpleAgent(Agent):
        pass

    provider = FakeProvider([Message(role=Role.ASSISTANT, content="hi")])
    executor = Executor(provider=provider)

    run = SimpleAgent.run("hello", executor=executor)

    assert run.status == RunStatus.COMPLETED
    assert provider.calls  # the explicit executor's provider was used


def test_run_async_accepts_an_explicit_async_executor_as_an_escape_hatch():
    class SimpleAgent(Agent):
        pass

    provider = FakeAsyncProvider([Message(role=Role.ASSISTANT, content="hi")])
    executor = AsyncExecutor(provider=provider)

    run = asyncio.run(SimpleAgent.run_async("hello", executor=executor))

    assert run.status == RunStatus.COMPLETED
    assert run.result == "hi"
    assert provider.calls  # the explicit executor's provider was used


def test_run_later_queues_and_runs_via_the_default_inline_queue():
    class SimpleAgent(Agent):
        pass

    configure(provider=FakeProvider([Message(role=Role.ASSISTANT, content="hi")]))

    run = SimpleAgent.run_later("hello")

    assert run.status == RunStatus.COMPLETED


def test_run_with_a_conversation_carries_history_into_the_next_run():
    class SimpleAgent(Agent):
        instructions = "Be terse."

    provider = FakeProvider(
        [
            Message(role=Role.ASSISTANT, content="Tokyo is sunny."),
            Message(role=Role.ASSISTANT, content="22 degrees."),
        ]
    )
    executor = Executor(provider=provider)
    conversation = Conversation()

    first = SimpleAgent.run(
        "What's the weather in Tokyo?", executor=executor, conversation=conversation
    )
    assert first.status == RunStatus.COMPLETED

    second = SimpleAgent.run(
        "And the temperature?", executor=executor, conversation=conversation
    )

    assert second.status == RunStatus.COMPLETED
    # second call's messages: system, first user+assistant turn, new user turn
    contents = [m.content for m in provider.calls[1]["messages"]]
    assert contents == [
        "Be terse.",
        "What's the weather in Tokyo?",
        "Tokyo is sunny.",
        "And the temperature?",
    ]
    assert conversation.messages[-1].content == "22 degrees."


def test_as_tool_defaults_name_and_description_from_the_agent():
    class ResearchAgent(Agent):
        instructions = "Research thoroughly."

    tool = ResearchAgent.as_tool()

    assert isinstance(tool, DelegateTool)
    assert tool.tool_name() == "ResearchAgent"
    assert tool.tool_description() == "Research thoroughly."


def test_as_tool_accepts_name_and_description_overrides():
    class ResearchAgent(Agent):
        instructions = "Research thoroughly."

    tool = ResearchAgent.as_tool(name="researcher", description="Looks things up.")

    assert tool.tool_name() == "researcher"
    assert tool.tool_description() == "Looks things up."


def test_delegate_tool_schema_is_a_single_input_field():
    class ResearchAgent(Agent):
        pass

    assert ResearchAgent.as_tool().schema() == {
        "type": "object",
        "properties": {"input": {"type": "string"}},
        "required": ["input"],
    }


def test_a_parent_agent_can_delegate_to_a_sub_agent():
    class ResearchAgent(Agent):
        instructions = "Research."

    provider = FakeProvider(
        [
            Message(
                role=Role.ASSISTANT,
                tool_calls=[
                    ToolCall(name="ResearchAgent", arguments={"input": "fusion energy"})
                ],
            ),
            Message(role=Role.ASSISTANT, content="Fusion is promising."),
            Message(role=Role.ASSISTANT, content="Fusion is promising, per research."),
        ]
    )
    executor = Executor(provider=provider)
    research_tool = ResearchAgent.as_tool(executor=executor)

    class LeadAgent(Agent):
        instructions = "Delegate research questions."
        tools = [research_tool]

    run = LeadAgent.run("What about fusion?", executor=executor)

    assert run.status == RunStatus.COMPLETED
    assert run.result == "Fusion is promising, per research."
    # the sub-run isn't folded into the parent's own event log, but it
    # stays reachable for direct inspection (manifesto §15)
    assert research_tool.last_run.status == RunStatus.COMPLETED
    assert research_tool.last_run.result == "Fusion is promising."


def test_a_delegated_run_that_fails_surfaces_as_a_failed_tool_call():
    class ResearchAgent(Agent):
        pass

    provider = FakeProvider(
        [
            Message(
                role=Role.ASSISTANT,
                tool_calls=[ToolCall(name="ResearchAgent", arguments={"input": "x"})],
            ),
        ]
    )
    executor = Executor(provider=provider)
    # ResearchAgent's own model call has no scripted response, so its Run fails
    research_tool = ResearchAgent.as_tool(executor=Executor(provider=FakeProvider([])))

    class LeadAgent(Agent):
        tools = [research_tool]

    run = LeadAgent.run("delegate this", executor=executor)

    # DefaultStrategy fails the parent run on the first tool error, same as
    # any other failing tool call would (see RetryStrategy for retries)
    assert run.status == RunStatus.FAILED
    failed_call = next(tc for tc in run.tool_calls if tc.name == "ResearchAgent")
    assert failed_call.error is not None
    # still reachable for inspection even though the delegated run failed
    assert research_tool.last_run.status == RunStatus.FAILED


def test_as_async_tool_defaults_name_and_description_from_the_agent():
    class ResearchAgent(Agent):
        instructions = "Research thoroughly."

    tool = ResearchAgent.as_async_tool()

    assert isinstance(tool, AsyncDelegateTool)
    assert tool.tool_name() == "ResearchAgent"
    assert tool.tool_description() == "Research thoroughly."


def test_async_delegate_tool_schema_is_a_single_input_field():
    class ResearchAgent(Agent):
        pass

    assert ResearchAgent.as_async_tool().schema() == {
        "type": "object",
        "properties": {"input": {"type": "string"}},
        "required": ["input"],
    }


def test_a_parent_agent_can_delegate_to_a_sub_agent_via_async_executor():
    class ResearchAgent(Agent):
        instructions = "Research."

    provider = FakeAsyncProvider(
        [
            Message(
                role=Role.ASSISTANT,
                tool_calls=[
                    ToolCall(name="ResearchAgent", arguments={"input": "fusion energy"})
                ],
            ),
            Message(role=Role.ASSISTANT, content="Fusion is promising."),
            Message(role=Role.ASSISTANT, content="Fusion is promising, per research."),
        ]
    )
    executor = AsyncExecutor(provider=provider)
    research_tool = ResearchAgent.as_async_tool(executor=executor)

    class LeadAgent(Agent):
        instructions = "Delegate research questions."
        tools = [research_tool]

    run = asyncio.run(LeadAgent.run_async("What about fusion?", executor=executor))

    assert run.status == RunStatus.COMPLETED
    assert run.result == "Fusion is promising, per research."
    # the sub-run isn't folded into the parent's own event log, but it
    # stays reachable for direct inspection (manifesto §15)
    assert research_tool.last_run.status == RunStatus.COMPLETED
    assert research_tool.last_run.result == "Fusion is promising."


def test_an_async_delegated_run_that_fails_surfaces_as_a_failed_tool_call():
    class ResearchAgent(Agent):
        pass

    provider = FakeAsyncProvider(
        [
            Message(
                role=Role.ASSISTANT,
                tool_calls=[ToolCall(name="ResearchAgent", arguments={"input": "x"})],
            ),
        ]
    )
    executor = AsyncExecutor(provider=provider)
    # ResearchAgent's own model call has no scripted response, so its Run fails
    research_tool = ResearchAgent.as_async_tool(
        executor=AsyncExecutor(provider=FakeAsyncProvider([]))
    )

    class LeadAgent(Agent):
        tools = [research_tool]

    run = asyncio.run(LeadAgent.run_async("delegate this", executor=executor))

    assert run.status == RunStatus.FAILED
    failed_call = next(tc for tc in run.tool_calls if tc.name == "ResearchAgent")
    assert failed_call.error is not None
    assert research_tool.last_run.status == RunStatus.FAILED


def test_async_delegate_tools_run_concurrently_under_async_executor():
    """AsyncDelegateTool delegates through AsyncExecutor instead of a thread,
    so two independent delegate calls in one model turn run as genuine
    concurrent async I/O — see AsyncExecutor's docstring for the batching
    this rides on."""

    class SlowAsyncProvider:
        def __init__(self, response: Message) -> None:
            self._response = response

        async def complete(self, *, messages, tools, model) -> Message:
            await asyncio.sleep(0.2)
            return self._response

    class ResearchAgentA(Agent):
        pass

    class ResearchAgentB(Agent):
        pass

    tool_a = ResearchAgentA.as_async_tool(
        executor=AsyncExecutor(
            provider=SlowAsyncProvider(Message(role=Role.ASSISTANT, content="a done"))
        )
    )
    tool_b = ResearchAgentB.as_async_tool(
        executor=AsyncExecutor(
            provider=SlowAsyncProvider(Message(role=Role.ASSISTANT, content="b done"))
        )
    )

    class LeadAgent(Agent):
        tools = [tool_a, tool_b]

    provider = FakeAsyncProvider(
        [
            Message(
                role=Role.ASSISTANT,
                tool_calls=[
                    ToolCall(name="ResearchAgentA", arguments={"input": "a"}),
                    ToolCall(name="ResearchAgentB", arguments={"input": "b"}),
                ],
            ),
            Message(role=Role.ASSISTANT, content="both done"),
        ]
    )
    executor = AsyncExecutor(provider=provider)

    start = time.monotonic()
    run = asyncio.run(LeadAgent.run_async("do both", executor=executor))
    elapsed = time.monotonic() - start

    assert run.status == RunStatus.COMPLETED
    # sequential delegation would take >= 0.4s; concurrent stays close to 0.2s
    assert elapsed < 0.35, f"delegate calls did not run concurrently (took {elapsed}s)"
