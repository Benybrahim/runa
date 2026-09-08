"""`runa.logging`: live `logging`-module output for a run, off the SDK's `RunHooks`/`AgentHooks`.

For a structured, persisted, queryable record of a run instead, see `runa.tracing` — that runs
unconditionally regardless of `hooks`; this module is just console/log lines while a run happens.
"""

import logging
from typing import Any

from agents import AgentHooks, RunHooks
from agents.items import ModelResponse, TResponseInputItem
from agents.run_context import AgentHookContext, RunContextWrapper
from agents.tool import Tool

logger = logging.getLogger("runa")

__all__ = [
    "AgentHooks",
    "LoggingAgentHooks",
    "LoggingRunHooks",
    "RunHooks",
]


class LoggingRunHooks(RunHooks[Any]):
    """Logs each lifecycle event of a run through the standard `logging` module.

    `Agent.run`/`run_sync` use an instance of this as the default `hooks`, so every run is
    logged without the caller having to ask; passing an explicit `hooks` overrides it.
    """

    async def on_agent_start(self, context: AgentHookContext[Any], agent: Any) -> None:
        """Log that `agent` is about to run."""
        logger.info("agent start: %s", agent.name)

    async def on_agent_end(self, context: AgentHookContext[Any], agent: Any, output: Any) -> None:
        """Log the final output `agent` produced."""
        logger.info("agent end: %s -> %r", agent.name, output)

    async def on_handoff(
        self, context: RunContextWrapper[Any], from_agent: Any, to_agent: Any
    ) -> None:
        """Log a handoff between agents."""
        logger.info("handoff: %s -> %s", from_agent.name, to_agent.name)

    async def on_tool_start(self, context: RunContextWrapper[Any], agent: Any, tool: Tool) -> None:
        """Log that `tool` is about to run."""
        logger.info("tool start: %s (%s)", tool.name, agent.name)

    async def on_tool_end(
        self, context: RunContextWrapper[Any], agent: Any, tool: Tool, result: object
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

    async def on_llm_end(
        self, context: RunContextWrapper[Any], agent: Any, response: ModelResponse
    ) -> None:
        """Log that `agent`'s model call returned."""
        logger.debug("llm end: %s", agent.name)


class LoggingAgentHooks(AgentHooks[Any]):
    """Logs the lifecycle events of a single agent through the standard `logging` module.

    Assign an instance to an `Agent` subclass's `hooks` class attribute to log that agent's
    own callbacks; unlike `LoggingRunHooks`, this is scoped to one agent rather than a run.
    """

    async def on_start(self, context: AgentHookContext[Any], agent: Any) -> None:
        """Log that `agent` is about to run."""
        logger.info("agent start: %s", agent.name)

    async def on_end(self, context: AgentHookContext[Any], agent: Any, output: Any) -> None:
        """Log the final output `agent` produced."""
        logger.info("agent end: %s -> %r", agent.name, output)

    async def on_handoff(self, context: RunContextWrapper[Any], agent: Any, source: Any) -> None:
        """Log that `source` handed off to `agent`."""
        logger.info("handoff: %s -> %s", source.name, agent.name)

    async def on_tool_start(self, context: RunContextWrapper[Any], agent: Any, tool: Tool) -> None:
        """Log that `tool` is about to run."""
        logger.info("tool start: %s (%s)", tool.name, agent.name)

    async def on_tool_end(
        self, context: RunContextWrapper[Any], agent: Any, tool: Tool, result: object
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

    async def on_llm_end(
        self, context: RunContextWrapper[Any], agent: Any, response: ModelResponse
    ) -> None:
        """Log that `agent`'s model call returned."""
        logger.debug("llm end: %s", agent.name)
