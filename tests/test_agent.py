import asyncio
import time

import pytest

from runa.agent import (
    Agent,
    AsyncDelegateAgent,
    DelegateAgent,
    DuplicateToolName,
    UnknownApprovalTool,
)
from runa.application import ProviderNotConfigured, application, configure
from runa.core import Conversation, EventType, Message, Role, Run, RunStatus, ToolCall
from runa.runtime import AsyncExecutor, Executor
from runa.tool import Tool
from tests.fakes import FakeAsyncProvider, FakeAsyncStreamingProvider, FakeProvider


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
    run = Run(input="hi")
    agent.before_run(run)
    agent.plan(run)
    agent.review(run)
    agent.after_run(run)


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


def test_agent_name_defaults_to_the_class_name():
    class ResearchAgent(Agent):
        pass

    assert ResearchAgent.agent_name() == "ResearchAgent"


def test_agent_name_can_be_overridden():
    class ResearchAgent(Agent):
        name = "researcher-v2"

    assert ResearchAgent.agent_name() == "researcher-v2"


def test_run_is_stamped_with_agent_nameentity_and_version():
    class ResearchAgent(Agent):
        version = "1.2.0"

    provider = FakeProvider([Message(role=Role.ASSISTANT, content="hi")])

    run = ResearchAgent.run("hello", executor=Executor(provider=provider))

    assert run.agent_name == "ResearchAgent"
    assert run.agent_version == "1.2.0"


def test_run_async_and_run_later_also_stamp_agent_nameentity():
    class ResearchAgent(Agent):
        pass

    configure(provider=FakeProvider([Message(role=Role.ASSISTANT, content="hi")]))
    later = ResearchAgent.run_later("hello")
    assert later.agent_name == "ResearchAgent"

    async_provider = FakeAsyncProvider([Message(role=Role.ASSISTANT, content="hi")])
    async_run = asyncio.run(
        ResearchAgent.run_async(
            "hello", executor=AsyncExecutor(provider=async_provider)
        )
    )
    assert async_run.agent_name == "ResearchAgent"


def test_run_raises_if_no_default_provider_and_no_executor(monkeypatch):
    monkeypatch.setattr(application.config, "provider", None)

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


def test_run_stream_yields_the_streamed_output_and_the_same_final_run():
    class SimpleAgent(Agent):
        pass

    provider = FakeAsyncStreamingProvider([Message(role=Role.ASSISTANT, content="hi")])
    executor = AsyncExecutor(provider=provider)

    async def collect():
        stream = SimpleAgent.run_stream("hello", executor=executor)
        chunks = [chunk.text async for chunk in stream]
        return chunks, stream.run

    chunks, run = asyncio.run(collect())

    assert "".join(chunks) == "hi"
    assert run.status == RunStatus.COMPLETED
    assert run.result == "hi"


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


def test_delegate_agent_defaults_name_and_description_from_the_agent():
    class ResearchAgent(Agent):
        instructions = "Research thoroughly."

    tool = DelegateAgent(ResearchAgent)

    assert tool.tool_name() == "ResearchAgent"
    assert tool.tool_description() == "Research thoroughly."


def test_delegations_resolves_a_bare_agent_class_like_delegate_agent():
    class ResearchAgent(Agent):
        instructions = "Research thoroughly."

    class LeadAgent(Agent):
        delegations = [ResearchAgent]

    tool = LeadAgent.resolved_tools()["ResearchAgent"]

    assert isinstance(tool, DelegateAgent)
    assert tool.tool_name() == "ResearchAgent"
    assert tool.tool_description() == "Research thoroughly."


def test_delegate_agent_schema_has_input_and_transfer_fields():
    class ResearchAgent(Agent):
        pass

    schema = DelegateAgent(ResearchAgent).schema()

    assert schema["required"] == ["input"]
    assert set(schema["properties"]) == {"input", "transfer"}


def test_duplicate_name_across_tools_and_delegations_raises():
    class ResearchAgent(Agent):
        pass

    class Clashing(Tool):
        name = "ResearchAgent"

        def call(self) -> None:
            pass

    with pytest.raises(DuplicateToolName):

        class LeadAgent(Agent):
            tools = [Clashing]
            delegations = [ResearchAgent]


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
    research_tool = DelegateAgent(ResearchAgent, executor=executor)

    class LeadAgent(Agent):
        instructions = "Delegate research questions."
        delegations = [research_tool]

    run = LeadAgent.run("What about fusion?", executor=executor)

    assert run.status == RunStatus.COMPLETED
    assert run.result == "Fusion is promising, per research."
    # the sub-run isn't folded into the parent's own event log, but it
    # stays reachable for direct inspection (manifesto §15)
    assert research_tool.last_run is not None
    assert research_tool.last_run.status == RunStatus.COMPLETED
    assert research_tool.last_run.result == "Fusion is promising."
    # the sub-agent's own Run carries its own identity, not the parent's
    assert research_tool.last_run.agent_name == "ResearchAgent"
    # ...but records which Run delegated to it (architecture.md §15)
    assert research_tool.last_run.parent_run_id == run.id


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
    research_tool = DelegateAgent(
        ResearchAgent, executor=Executor(provider=FakeProvider([]))
    )

    class LeadAgent(Agent):
        delegations = [research_tool]

    run = LeadAgent.run("delegate this", executor=executor)

    # DefaultStrategy fails the parent run on the first tool error, same as
    # any other failing tool call would (see RetryStrategy for retries)
    assert run.status == RunStatus.FAILED
    failed_call = next(tc for tc in run.tool_calls if tc.name == "ResearchAgent")
    assert failed_call.error is not None
    # still reachable for inspection even though the delegated run failed
    assert research_tool.last_run is not None
    assert research_tool.last_run.status == RunStatus.FAILED


def test_transfer_false_argument_still_goes_through_the_return_path():
    """`call()` accepts `transfer` (unused) so a scripted transfer=false
    argument, or none at all, doesn't crash the ordinary Return path."""

    class ResearchAgent(Agent):
        pass

    provider = FakeProvider(
        [
            Message(
                role=Role.ASSISTANT,
                tool_calls=[
                    ToolCall(
                        name="ResearchAgent",
                        arguments={"input": "x", "transfer": False},
                    )
                ],
            ),
            Message(role=Role.ASSISTANT, content="answer"),
            Message(role=Role.ASSISTANT, content="answer, relayed"),
        ]
    )
    executor = Executor(provider=provider)
    research_tool = DelegateAgent(ResearchAgent, executor=executor)

    class LeadAgent(Agent):
        delegations = [research_tool]

    run = LeadAgent.run("go", executor=executor)

    assert run.status == RunStatus.COMPLETED
    assert run.result == "answer, relayed"
    assert research_tool.last_run is not None  # the nested Run actually ran


def test_transfer_swaps_the_active_agent():
    class SupportAgent(Agent):
        instructions = "You are support. Help directly."

    class TriageAgent(Agent):
        instructions = "Route billing questions to support."
        delegations = [SupportAgent]

    provider = FakeProvider(
        [
            Message(
                role=Role.ASSISTANT,
                tool_calls=[
                    ToolCall(
                        name="SupportAgent",
                        arguments={"input": "billing issue", "transfer": True},
                    )
                ],
            ),
            Message(role=Role.ASSISTANT, content="Sure, let's sort out your billing."),
        ]
    )
    executor = Executor(provider=provider)

    run = TriageAgent.run("I have a billing issue.", executor=executor)

    assert run.status == RunStatus.COMPLETED
    assert run.result == "Sure, let's sort out your billing."
    # provenance (who this Run was given to) survives the handoff...
    assert run.agent_name == "TriageAgent"
    # ...but who's currently driving it reflects the transfer
    assert run.active_agent_name == "SupportAgent"
    # the new agent's own instructions reach the model as a fresh system message
    final_call_contents = [m.content for m in provider.calls[-1]["messages"]]
    assert "You are support. Help directly." in final_call_contents


def test_transfer_emits_agent_transferred_event():
    class SupportAgent(Agent):
        pass

    class TriageAgent(Agent):
        delegations = [SupportAgent]

    provider = FakeProvider(
        [
            Message(
                role=Role.ASSISTANT,
                tool_calls=[
                    ToolCall(
                        name="SupportAgent", arguments={"input": "x", "transfer": True}
                    )
                ],
            ),
            Message(role=Role.ASSISTANT, content="done"),
        ]
    )

    run = TriageAgent.run("help", executor=Executor(provider=provider))

    event = next(e for e in run.events if e.type == EventType.AGENT_TRANSFERRED)
    assert event.data["from_agent"] == "TriageAgent"
    assert event.data["to_agent"] == "SupportAgent"


def test_async_delegate_agent_defaults_name_and_description_from_the_agent():
    class ResearchAgent(Agent):
        instructions = "Research thoroughly."

    tool = AsyncDelegateAgent(ResearchAgent)

    assert tool.tool_name() == "ResearchAgent"
    assert tool.tool_description() == "Research thoroughly."


def test_async_delegate_agent_schema_has_input_and_transfer_fields():
    class ResearchAgent(Agent):
        pass

    schema = AsyncDelegateAgent(ResearchAgent).schema()

    assert schema["required"] == ["input"]
    assert set(schema["properties"]) == {"input", "transfer"}


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
    research_tool = AsyncDelegateAgent(ResearchAgent, executor=executor)

    class LeadAgent(Agent):
        instructions = "Delegate research questions."
        delegations = [research_tool]

    run = asyncio.run(LeadAgent.run_async("What about fusion?", executor=executor))

    assert run.status == RunStatus.COMPLETED
    assert run.result == "Fusion is promising, per research."
    # the sub-run isn't folded into the parent's own event log, but it
    # stays reachable for direct inspection (manifesto §15)
    assert research_tool.last_run is not None
    assert research_tool.last_run.status == RunStatus.COMPLETED
    assert research_tool.last_run.result == "Fusion is promising."
    assert research_tool.last_run.parent_run_id == run.id


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
    research_tool = AsyncDelegateAgent(
        ResearchAgent, executor=AsyncExecutor(provider=FakeAsyncProvider([]))
    )

    class LeadAgent(Agent):
        delegations = [research_tool]

    run = asyncio.run(LeadAgent.run_async("delegate this", executor=executor))

    assert run.status == RunStatus.FAILED
    failed_call = next(tc for tc in run.tool_calls if tc.name == "ResearchAgent")
    assert failed_call.error is not None
    assert research_tool.last_run is not None
    assert research_tool.last_run.status == RunStatus.FAILED


def test_async_delegate_agents_run_concurrently_under_async_executor():
    """AsyncDelegateAgent delegates through AsyncExecutor instead of a thread,
    so two independent delegate calls in one model turn run as genuine
    concurrent async I/O; see AsyncExecutor's docstring for the batching
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

    tool_a = AsyncDelegateAgent(
        ResearchAgentA,
        executor=AsyncExecutor(
            provider=SlowAsyncProvider(Message(role=Role.ASSISTANT, content="a done"))
        ),
    )
    tool_b = AsyncDelegateAgent(
        ResearchAgentB,
        executor=AsyncExecutor(
            provider=SlowAsyncProvider(Message(role=Role.ASSISTANT, content="b done"))
        ),
    )

    class LeadAgent(Agent):
        delegations = [tool_a, tool_b]

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


def test_a_denying_policy_fails_the_run_without_calling_the_tool_or_a_human():
    calls = []

    class TrackedTool(Tool):
        def call(self) -> None:
            calls.append("called")

    def deny_everything(run, tool_call):
        return False

    class FinanceAgent(Agent):
        tools = [TrackedTool]
        policies = [deny_everything]

    provider = FakeProvider(
        [Message(role=Role.ASSISTANT, tool_calls=[ToolCall(name="TrackedTool")])]
    )

    run = FinanceAgent.run("do it", executor=Executor(provider=provider))

    assert run.status == RunStatus.FAILED
    assert not calls  # the tool itself never ran
    assert EventType.POLICY_DENIED in [event.type for event in run.events]


def test_a_policy_runs_before_approval_so_a_denied_call_never_pauses_for_a_human():
    class TransferFunds(Tool):
        def call(self, amount: float) -> None:
            pass

    def deny_large_transfers(run, tool_call):
        return tool_call.arguments.get("amount", 0) <= 100

    class FinanceAgent(Agent):
        tools = [TransferFunds]
        requires_approval = [TransferFunds]
        policies = [deny_large_transfers]

    provider = FakeProvider(
        [
            Message(
                role=Role.ASSISTANT,
                tool_calls=[
                    ToolCall(name="TransferFunds", arguments={"amount": 10_000})
                ],
            )
        ]
    )

    run = FinanceAgent.run("transfer", executor=Executor(provider=provider))

    assert run.status == RunStatus.FAILED  # denied outright, never AWAITING_APPROVAL


def test_a_passing_policy_lets_the_tool_call_proceed():
    class TrackedTool(Tool):
        def call(self) -> None:
            pass

    class FinanceAgent(Agent):
        tools = [TrackedTool]
        policies = [lambda run, tool_call: True]

    provider = FakeProvider(
        [
            Message(role=Role.ASSISTANT, tool_calls=[ToolCall(name="TrackedTool")]),
            Message(role=Role.ASSISTANT, content="done"),
        ]
    )

    run = FinanceAgent.run("do it", executor=Executor(provider=provider))

    assert run.status == RunStatus.COMPLETED


def test_a_denying_policy_fails_an_async_run_without_calling_the_tool():
    calls = []

    class TrackedTool(Tool):
        async def call(self) -> None:
            calls.append("called")

    def deny_everything(run, tool_call):
        return False

    class FinanceAgent(Agent):
        tools = [TrackedTool]
        policies = [deny_everything]

    provider = FakeAsyncProvider(
        [Message(role=Role.ASSISTANT, tool_calls=[ToolCall(name="TrackedTool")])]
    )

    run = asyncio.run(
        FinanceAgent.run_async("do it", executor=AsyncExecutor(provider=provider))
    )

    assert run.status == RunStatus.FAILED
    assert not calls
    assert EventType.POLICY_DENIED in [event.type for event in run.events]
