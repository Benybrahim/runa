"""Logic shared by `Executor` (see `runtime/executor.py`).

`seed_run`, `model_context`, and `tool_schemas` don't touch any Executor
instance state, so they live here rather than as methods on the class.
"""

from typing import TYPE_CHECKING, Any

from runa.core import (
    Conversation,
    EffectStatus,
    EventType,
    Message,
    Role,
    Run,
    ToolCall,
)
from runa.tool import DelegatesToAgent

if TYPE_CHECKING:
    from runa.agent import Agent


def seed_run(
    agent: "Agent", run: Run, conversation: Conversation | None = None
) -> None:
    # Stamped here, not in Agent.run()/run_later()/DelegateAgent, so every
    # Run gets provenance (architecture.md §14) regardless of how it was
    # constructed, including a Run driven straight through Executor as
    # an escape hatch, and a sub-agent's own Run under delegation.
    run.agent_name = agent.agent_name()
    run.agent_version = agent.version
    # `agent_name`/`agent_version` stay "who this Run was originally given
    # to"; a Transfer delegation (see transfer_agent) only ever updates the
    # active_* pair below, so original provenance and "who's currently
    # driving" (name and version both) stay distinct.
    run.active_agent_name = agent.agent_name()
    run.active_agent_version = agent.version
    run.conversation_id = conversation.id if conversation is not None else None
    if agent.instructions:
        run.add_message(Message(role=Role.SYSTEM, content=agent.instructions))
    run.add_message(Message(role=Role.USER, content=str(run.input)))


def model_context(run: Run, conversation: Conversation | None) -> list[Message]:
    """The messages to send to the model for `run`'s next call.

    A projection assembled at call time, not a stored object (RUNA.md):
    this Run's own system prompt (if any), then the Conversation's durable
    cross-Run history, then the rest of this Run's own messages. Neither
    `run.messages` nor `conversation.messages` is mutated to build this;
    recomputing it on every call means a Run paused mid-flight sees any
    turns recorded into `conversation` in the meantime, rather than a
    stale copy taken when the Run started.

    The system prompt, if `seed_run` added one, is always `run.messages[0]`
    (nothing runs before it); history is inserted right after it rather
    than prepended in front of it, so the model still sees its
    instructions first. A later SYSTEM message from a Transfer delegation
    (see `transfer_agent`) isn't touched by this: it isn't `run.messages[0]`,
    so it stays wherever it naturally falls in "the rest of this Run's own
    messages", in the order it was actually added.
    """
    if conversation is None:
        return list(run.messages)
    if run.messages and run.messages[0].role == Role.SYSTEM:
        return [run.messages[0], *conversation.messages, *run.messages[1:]]
    return [*conversation.messages, *run.messages]


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
    transferred-to agent gets it, not the original. `run.active_agent_name`
    and `run.active_agent_version` both update to the new agent's identity,
    so provenance reflects which Agent definition actually produced the
    rest of the transcript, not just which one the Run started with
    (`run.agent_name`/`run.agent_version`, untouched here).
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
    run.active_agent_version = new_agent.version
    run.add_message(
        Message(
            role=Role.TOOL, content=str(tool_call.result), tool_call_id=tool_call.id
        )
    )
    if new_agent.instructions:
        run.add_message(Message(role=Role.SYSTEM, content=new_agent.instructions))
    return new_agent
