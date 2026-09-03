"""Logic shared between the sync and async Executors.

`seed_run` and `tool_schemas` don't touch any Executor instance state, so
both `Executor` and `AsyncExecutor` call these instead of each defining
their own copy.
"""

from typing import TYPE_CHECKING, Any

from runa.core import Context, Message, Role, Run

if TYPE_CHECKING:
    from runa.agent import Agent


def render_context(context: Context) -> str:
    """A plain "key: value" rendering of `context`, one line per entry.

    Context is deliberately free-form (architecture.md §2) — any key an
    application sets should reach the Agent the same generic way, with
    nothing in the framework interpreting specific key names specially. An
    application whose Context needs a different shape in the prompt keeps
    the escape hatch: don't populate `run.context`, and build the message
    directly in `before_run`/`plan` instead.
    """
    lines = "\n".join(f"{key}: {value}" for key, value in context.items())
    return f"Context:\n{lines}"


def seed_run(agent: "Agent", run: Run) -> None:
    # Stamped here, not in Agent.run()/run_later()/DelegateTool, so every
    # Run gets provenance (architecture.md §14) regardless of how it was
    # constructed — including a Run driven straight through Executor as
    # an escape hatch, and a sub-agent's own Run under delegation.
    run.agent_name = agent.agent_name()
    run.agent_version = agent.version
    if agent.instructions:
        run.add_message(Message(role=Role.SYSTEM, content=agent.instructions))
    if run.context:
        run.add_message(Message(role=Role.SYSTEM, content=render_context(run.context)))
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
