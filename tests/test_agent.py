import pytest

from runa.agent import Agent, DuplicateToolName, UnknownApprovalTool
from runa.tool import Tool


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
