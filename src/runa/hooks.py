"""Built-in `RunHooks` implementations."""

import logging
import time
from dataclasses import dataclass
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


class TracingRunHooks(RunHooks[Any]):
    """Logs each lifecycle event of a run with the elapsed time since its matching start.

    Complements `LoggingRunHooks`, which logs that an event happened, by also logging how long
    it took: each `on_*_end` callback logs the elapsed time since the matching `on_*_start`.
    """

    def __init__(self) -> None:
        """Initialize the start-time stacks used to pair `on_*_start`/`on_*_end` callbacks."""
        self._agent_starts: list[float] = []
        self._tool_starts: list[float] = []
        self._llm_starts: list[float] = []

    async def on_agent_start(self, context: AgentHookContext[Any], agent: Any) -> None:
        """Log that `agent` is about to run and record the start time."""
        self._agent_starts.append(time.monotonic())
        logger.info("agent start: %s", agent.name)

    async def on_agent_end(self, context: AgentHookContext[Any], agent: Any, output: Any) -> None:
        """Log the final output `agent` produced and the elapsed time since it started."""
        elapsed_ms = (time.monotonic() - self._agent_starts.pop()) * 1000
        logger.info("agent end: %s -> %r (%.1fms)", agent.name, output, elapsed_ms)

    async def on_handoff(
        self, context: RunContextWrapper[Any], from_agent: Any, to_agent: Any
    ) -> None:
        """Log a handoff between agents."""
        logger.info("handoff: %s -> %s", from_agent.name, to_agent.name)

    async def on_tool_start(self, context: RunContextWrapper[Any], agent: Any, tool: Tool) -> None:
        """Log that `tool` is about to run and record the start time."""
        self._tool_starts.append(time.monotonic())
        logger.info("tool start: %s (%s)", tool.name, agent.name)

    async def on_tool_end(
        self, context: RunContextWrapper[Any], agent: Any, tool: Tool, result: object
    ) -> None:
        """Log the result `tool` returned and the elapsed time since it started."""
        elapsed_ms = (time.monotonic() - self._tool_starts.pop()) * 1000
        logger.info("tool end: %s -> %r (%.1fms)", tool.name, result, elapsed_ms)

    async def on_llm_start(
        self,
        context: RunContextWrapper[Any],
        agent: Any,
        system_prompt: str | None,
        input_items: list[TResponseInputItem],
    ) -> None:
        """Log that `agent` is about to call the model and record the start time."""
        self._llm_starts.append(time.monotonic())
        logger.debug("llm start: %s", agent.name)

    async def on_llm_end(
        self, context: RunContextWrapper[Any], agent: Any, response: ModelResponse
    ) -> None:
        """Log that `agent`'s model call returned and the elapsed time since it started."""
        elapsed_ms = (time.monotonic() - self._llm_starts.pop()) * 1000
        logger.debug("llm end: %s (%.1fms)", agent.name, elapsed_ms)


@dataclass(frozen=True)
class AuditEvent:
    """A single timestamped entry in an `AuditRunHooks` trail."""

    timestamp: float
    """The `time.time()` value when the event occurred."""

    event: str
    """The lifecycle callback that produced this entry, e.g. `"tool_end"`."""

    agent: str
    """The name of the agent involved in the event."""

    detail: str
    """A human-readable description of the event's payload."""


class AuditRunHooks(RunHooks[Any]):
    """Records each lifecycle event of a run as a timestamped `AuditEvent`.

    Unlike `LoggingRunHooks`, which only logs each event, or `MetricsRunHooks`, which only
    counts them, this keeps the full sequence in `events` so a caller can inspect or export the
    trail once the run completes.
    """

    def __init__(self) -> None:
        """Initialize an empty audit trail."""
        self.events: list[AuditEvent] = []

    def _record(self, event: str, agent: Any, detail: str) -> None:
        self.events.append(AuditEvent(time.time(), event, agent.name, detail))

    async def on_agent_start(self, context: AgentHookContext[Any], agent: Any) -> None:
        """Record that `agent` is about to run."""
        self._record("agent_start", agent, "start")

    async def on_agent_end(self, context: AgentHookContext[Any], agent: Any, output: Any) -> None:
        """Record the final output `agent` produced."""
        self._record("agent_end", agent, repr(output))

    async def on_handoff(
        self, context: RunContextWrapper[Any], from_agent: Any, to_agent: Any
    ) -> None:
        """Record a handoff between agents."""
        self._record("handoff", to_agent, f"from {from_agent.name}")

    async def on_tool_start(self, context: RunContextWrapper[Any], agent: Any, tool: Tool) -> None:
        """Record that `tool` is about to run."""
        self._record("tool_start", agent, tool.name)

    async def on_tool_end(
        self, context: RunContextWrapper[Any], agent: Any, tool: Tool, result: object
    ) -> None:
        """Record the result `tool` returned."""
        self._record("tool_end", agent, f"{tool.name} -> {result!r}")

    async def on_llm_start(
        self,
        context: RunContextWrapper[Any],
        agent: Any,
        system_prompt: str | None,
        input_items: list[TResponseInputItem],
    ) -> None:
        """Record that `agent` is about to call the model."""
        self._record("llm_start", agent, "start")

    async def on_llm_end(
        self, context: RunContextWrapper[Any], agent: Any, response: ModelResponse
    ) -> None:
        """Record that `agent`'s model call returned."""
        self._record("llm_end", agent, "end")


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
