"""Logic shared between the sync and async Executors.

`seed_run` and `tool_schemas` don't touch any Executor instance state, so
both `Executor` and `AsyncExecutor` call these instead of each defining
their own copy.
"""

from typing import TYPE_CHECKING, Any

from runa.core import Message, Role, Run

if TYPE_CHECKING:
    from runa.agent import Agent


def seed_run(agent: "Agent", run: Run) -> None:
    # Stamped here, not in Agent.run()/run_later()/DelegateTool, so every
    # Run gets provenance (architecture.md §14) regardless of how it was
    # constructed — including a Run driven straight through Executor as
    # an escape hatch, and a sub-agent's own Run under delegation.
    run.agent_id = agent.agent_name()
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
