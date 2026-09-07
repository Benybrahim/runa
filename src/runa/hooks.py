"""Built-in `RunHooks` implementations."""

import logging
from typing import Any

from agents import AgentHooks, RunHooks
from agents.items import ModelResponse, TResponseInputItem
from agents.run_context import AgentHookContext, RunContextWrapper
from agents.tool import Tool
from agents.usage import Usage

logger = logging.getLogger("runa")


class LoggingRunHooks(RunHooks[Any]):
    """Logs each lifecycle event of a run through the standard `logging` module.

    `Agent.run`/`run_sync` use an instance of this as the default `hooks` so every run is
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


class MetricsRunHooks(RunHooks[Any]):
    """Counts each lifecycle event of a run and accumulates model token usage.

    Unlike `LoggingRunHooks`, which logs each event, this accumulates them into attributes an
    instance exposes so a caller can inspect them once the run completes.
    """

    def __init__(self) -> None:
        """Initialize every counter and the token usage total to zero."""
        self.agent_starts = 0
        self.agent_ends = 0
        self.handoffs = 0
        self.tool_starts = 0
        self.tool_ends = 0
        self.llm_starts = 0
        self.llm_ends = 0
        self.usage = Usage()

    async def on_agent_start(self, context: AgentHookContext[Any], agent: Any) -> None:
        """Count that `agent` is about to run."""
        self.agent_starts += 1

    async def on_agent_end(self, context: AgentHookContext[Any], agent: Any, output: Any) -> None:
        """Count the final output `agent` produced."""
        self.agent_ends += 1

    async def on_handoff(
        self, context: RunContextWrapper[Any], from_agent: Any, to_agent: Any
    ) -> None:
        """Count a handoff between agents."""
        self.handoffs += 1

    async def on_tool_start(self, context: RunContextWrapper[Any], agent: Any, tool: Tool) -> None:
        """Count that `tool` is about to run."""
        self.tool_starts += 1

    async def on_tool_end(
        self, context: RunContextWrapper[Any], agent: Any, tool: Tool, result: object
    ) -> None:
        """Count the result `tool` returned."""
        self.tool_ends += 1

    async def on_llm_start(
        self,
        context: RunContextWrapper[Any],
        agent: Any,
        system_prompt: str | None,
        input_items: list[TResponseInputItem],
    ) -> None:
        """Count that `agent` is about to call the model."""
        self.llm_starts += 1

    async def on_llm_end(
        self, context: RunContextWrapper[Any], agent: Any, response: ModelResponse
    ) -> None:
        """Count `agent`'s model call and accumulate its token usage."""
        self.llm_ends += 1
        self.usage.add(response.usage)


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
