"""Logic shared by `Executor` (see `runtime/executor.py`).

`seed_run` and `tool_schemas` don't touch any Executor instance state, so
they live here rather than as methods on the class.
"""

from typing import TYPE_CHECKING, Any

from runa.core import EffectStatus, EventType, Message, Role, Run, ToolCall
from runa.tool import DelegatesToAgent

if TYPE_CHECKING:
    from runa.agent import Agent


def seed_run(agent: "Agent", run: Run) -> None:
    # Stamped here, not in Agent.run()/run_later()/DelegateAgent, so every
    # Run gets provenance (architecture.md §14) regardless of how it was
    # constructed, including a Run driven straight through Executor as
    # an escape hatch, and a sub-agent's own Run under delegation.
    run.agent_name = agent.agent_name()
    # `agent_name` stays "who this Run was originally given to"; a Transfer
    # delegation (see transfer_agent) only ever updates this field, not
    # agent_name, so provenance and "who's currently driving" stay distinct.
    run.active_agent_name = agent.agent_name()
    run.agent_version = agent.version
    if agent.instructions:
        run.add_message(Message(role=Role.SYSTEM, content=agent.instructions))
    if run.conversation is not None:
        run.messages.extend(run.conversation.messages)
    run.add_message(Message(role=Role.USER, content=str(run.input)))


def tool_schemas(agent: "Agent") -> list[dict[str, Any]]:
    return [
        {
            "name": name,
            "description": tool.tool_description(),
            "parameters": tool.schema(),
        }
        for name, tool in agent.resolved_tools().items()
    ]


def transfer_agent(
    agent: "Agent", run: Run, tool: DelegatesToAgent, tool_call: ToolCall
) -> "Agent":
    """Hand control of `run` to the Agent `tool` wraps (a transfer=true call).

    Shared by `Executor`'s `_call_tool`/`_call_tools`. Unlike a Return
    delegation, this doesn't create a nested Run: `run` itself keeps going,
    driven by a fresh instance of the delegated Agent from here on. The tool
    call still gets a normal TOOL-role result message (every tool call needs
    one), followed by a SYSTEM message carrying the new agent's instructions,
    the same way `seed_run` introduces the first agent's instructions, so the
    model sees the new persona on its next turn. `agent.after_run()`
    fires on whichever agent is active when `run` completes, so a
    transferred-to agent gets it, not the original.
    """
    new_agent = tool.new_agent_instance()
    tool_call.attempts += 1
    tool_call.error = None
    tool_call.effect = EffectStatus.OBSERVED
    tool_call.result = f"transferred to {new_agent.agent_name()}"
    run.emit(
        EventType.AGENT_TRANSFERRED,
        tool_call_id=tool_call.id,
        from_agent=agent.agent_name(),
        to_agent=new_agent.agent_name(),
    )
    run.active_agent_name = new_agent.agent_name()
    run.add_message(
        Message(
            role=Role.TOOL, content=str(tool_call.result), tool_call_id=tool_call.id
        )
    )
    if new_agent.instructions:
        run.add_message(Message(role=Role.SYSTEM, content=new_agent.instructions))
    return new_agent
