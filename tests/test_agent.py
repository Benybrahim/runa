import pytest

from runa.agent import Agent, DuplicateToolName, UnknownApprovalTool
from runa.config import ProviderNotConfigured, configure
from runa.core import Message, Role, RunStatus
from runa.runtime import Executor
from runa.tool import Tool
from tests.fakes import FakeProvider


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


def test_run_later_queues_and_runs_via_the_default_inline_queue():
    class SimpleAgent(Agent):
        pass

    configure(provider=FakeProvider([Message(role=Role.ASSISTANT, content="hi")]))

    run = SimpleAgent.run_later("hello")

    assert run.status == RunStatus.COMPLETED
