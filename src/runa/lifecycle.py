"""`runa.lifecycle`: `RunHooks`/`AgentHooks`, and live `logging`-module output for a run.

For a structured, persisted, queryable record of a run instead, see `runa.tracing`. That runs
unconditionally regardless of `hooks`; this module is just console/log lines while a run happens.
"""

from __future__ import annotations

import logging
from typing import Any

from runa._types import RunContextWrapper, TResponseInputItem
from runa.tool import FunctionTool

logger = logging.getLogger("runa")

__all__ = [
    "AgentHooks",
    "LoggingAgentHooks",
    "LoggingRunHooks",
    "RunHooks",
]


class RunHooks[TContext]:
    """Lifecycle callbacks for one run; every method is a no-op unless overridden.

    Passed as `hooks=` to `Agent.run`/`run_sync`/`run_streamed`, `runa.run_internal` calls these
    as the run progresses. `LoggingRunHooks` (below) is the default when no `hooks` is given.
    """

    async def on_agent_start(self, context: RunContextWrapper[TContext], agent: Any) -> None:
        """Called right before `agent` starts (or resumes, after a handoff) running."""

    async def on_agent_end(
        self, context: RunContextWrapper[TContext], agent: Any, output: Any
    ) -> None:
        """Called once `agent` has produced its final output for the run."""

    async def on_handoff(
        self, context: RunContextWrapper[TContext], from_agent: Any, to_agent: Any
    ) -> None:
        """Called when `from_agent` hands the run off to `to_agent`."""

    async def on_tool_start(
        self, context: RunContextWrapper[TContext], agent: Any, tool: FunctionTool
    ) -> None:
        """Called right before `tool` runs."""

    async def on_tool_end(
        self, context: RunContextWrapper[TContext], agent: Any, tool: FunctionTool, result: object
    ) -> None:
        """Called once `tool` has returned (or raised) `result`."""

    async def on_llm_start(
        self,
        context: RunContextWrapper[TContext],
        agent: Any,
        system_prompt: str | None,
        input_items: list[TResponseInputItem],
    ) -> None:
        """Called right before `agent` calls the model."""

    async def on_llm_end(
        self, context: RunContextWrapper[TContext], agent: Any, response: Any
    ) -> None:
        """Called once the model call has returned `response`."""


class AgentHooks[TContext]:
    """Lifecycle callbacks scoped to one `Agent` subclass, via its `hooks` class attribute.

    Every method is a no-op unless overridden. Unlike `RunHooks` (passed per-call), this fires
    only for the agent it's assigned to, not for every agent in a run with handoffs/delegates.
    """

    async def on_start(self, context: RunContextWrapper[TContext], agent: Any) -> None:
        """Called right before this agent starts (or resumes, after a handoff) running."""

    async def on_end(self, context: RunContextWrapper[TContext], agent: Any, output: Any) -> None:
        """Called once this agent has produced its final output for the run."""

    async def on_handoff(
        self, context: RunContextWrapper[TContext], agent: Any, source: Any
    ) -> None:
        """Called when `source` hands the run off to this agent."""

    async def on_tool_start(
        self, context: RunContextWrapper[TContext], agent: Any, tool: FunctionTool
    ) -> None:
        """Called right before `tool` runs."""

    async def on_tool_end(
        self, context: RunContextWrapper[TContext], agent: Any, tool: FunctionTool, result: object
    ) -> None:
        """Called once `tool` has returned (or raised) `result`."""

    async def on_llm_start(
        self,
        context: RunContextWrapper[TContext],
        agent: Any,
        system_prompt: str | None,
        input_items: list[TResponseInputItem],
    ) -> None:
        """Called right before this agent calls the model."""

    async def on_llm_end(
        self, context: RunContextWrapper[TContext], agent: Any, response: Any
    ) -> None:
        """Called once the model call has returned `response`."""


class LoggingRunHooks(RunHooks[Any]):
    """Logs each lifecycle event of a run through the standard `logging` module.

    `Agent.run`/`run_sync` use an instance of this as the default `hooks`, so every run is
    logged without the caller having to ask; passing an explicit `hooks` overrides it.
    """

    async def on_agent_start(self, context: RunContextWrapper[Any], agent: Any) -> None:
        """Log that `agent` is about to run."""
        logger.info("agent start: %s", agent.name)

    async def on_agent_end(self, context: RunContextWrapper[Any], agent: Any, output: Any) -> None:
        """Log the final output `agent` produced."""
        logger.info("agent end: %s -> %r", agent.name, output)

    async def on_handoff(
        self, context: RunContextWrapper[Any], from_agent: Any, to_agent: Any
    ) -> None:
        """Log a handoff between agents."""
        logger.info("handoff: %s -> %s", from_agent.name, to_agent.name)

    async def on_tool_start(
        self, context: RunContextWrapper[Any], agent: Any, tool: FunctionTool
    ) -> None:
        """Log that `tool` is about to run."""
        logger.info("tool start: %s (%s)", tool.name, agent.name)

    async def on_tool_end(
        self, context: RunContextWrapper[Any], agent: Any, tool: FunctionTool, result: object
    ) -> None:
        """Log the result `tool` returned."""
        logger.info("tool end: %s -> %r", tool.name, result)

    async def on_llm_start(
        self,
        context: RunContextWrapper[Any],
        agent: Any,
        system_prompt: str | None,
        input_items: list[TResponseInputItem],
    ) -> None:
        """Log that `agent` is about to call the model."""
        logger.debug("llm start: %s", agent.name)

    async def on_llm_end(self, context: RunContextWrapper[Any], agent: Any, response: Any) -> None:
        """Log that `agent`'s model call returned."""
        logger.debug("llm end: %s", agent.name)


class LoggingAgentHooks(AgentHooks[Any]):
    """Logs the lifecycle events of a single agent through the standard `logging` module.

    Assign an instance to an `Agent` subclass's `hooks` class attribute to log that agent's
    own callbacks; unlike `LoggingRunHooks`, this is scoped to one agent rather than a run.
    """

    async def on_start(self, context: RunContextWrapper[Any], agent: Any) -> None:
        """Log that `agent` is about to run."""
        logger.info("agent start: %s", agent.name)

    async def on_end(self, context: RunContextWrapper[Any], agent: Any, output: Any) -> None:
        """Log the final output `agent` produced."""
        logger.info("agent end: %s -> %r", agent.name, output)

    async def on_handoff(self, context: RunContextWrapper[Any], agent: Any, source: Any) -> None:
        """Log that `source` handed off to `agent`."""
        logger.info("handoff: %s -> %s", source.name, agent.name)

    async def on_tool_start(
        self, context: RunContextWrapper[Any], agent: Any, tool: FunctionTool
    ) -> None:
        """Log that `tool` is about to run."""
        logger.info("tool start: %s (%s)", tool.name, agent.name)

    async def on_tool_end(
        self, context: RunContextWrapper[Any], agent: Any, tool: FunctionTool, result: object
    ) -> None:
        """Log the result `tool` returned."""
        logger.info("tool end: %s -> %r", tool.name, result)

    async def on_llm_start(
        self,
        context: RunContextWrapper[Any],
        agent: Any,
        system_prompt: str | None,
        input_items: list[TResponseInputItem],
    ) -> None:
        """Log that `agent` is about to call the model."""
        logger.debug("llm start: %s", agent.name)

    async def on_llm_end(self, context: RunContextWrapper[Any], agent: Any, response: Any) -> None:
        """Log that `agent`'s model call returned."""
        logger.debug("llm end: %s", agent.name)
