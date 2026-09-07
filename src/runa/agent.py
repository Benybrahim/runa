"""Class-based Agent built on the OpenAI Agents SDK."""

import inspect
from collections.abc import AsyncIterator
from dataclasses import MISSING, dataclass, fields, replace
from typing import Any, Literal

from agents import Agent as BaseAgent
from agents import RunConfig, RunContextWrapper, RunHooks, Runner, StreamEvent
from agents import responses_websocket_session as websocket_session
from agents.extensions.models.litellm_provider import LitellmProvider
from agents.items import TResponseInputItem
from agents.responses_websocket_session import ResponsesWebSocketSession

from runa.guardrail import flatten_agent_guardrails
from runa.hooks import (
    AuditRunHooks,
    CompositeRunHooks,
    LoggingRunHooks,
    MetricsRunHooks,
    TracingRunHooks,
)

_RUN_CONFIG = RunConfig(model_provider=LitellmProvider())


def _default_hooks() -> RunHooks[Any]:
    """Build a fresh composite of every built-in `RunHooks`.

    `MetricsRunHooks`, `TracingRunHooks`, and `AuditRunHooks` accumulate per-run state, so a
    new instance is built for each call instead of sharing one across runs.
    """
    return CompositeRunHooks(
        LoggingRunHooks(), MetricsRunHooks(), TracingRunHooks(), AuditRunHooks()
    )


def _adapt_instructions(instructions: Any) -> Any:
    """Let `instructions` be a `(context) -> str` callable instead of the SDK's `(context, agent)`.

    The SDK calls `instructions(run_context, agent)` and requires exactly two parameters. A
    single-parameter callable is wrapped so it receives just `run_context.context`, the object
    passed to `Agent.run`/`run_sync`; anything else (a string, `None`, or an already
    two-parameter callable) passes through unchanged.
    """
    if not callable(instructions):
        return instructions
    params = list(inspect.signature(instructions).parameters.values())
    if len(params) != 1:
        return instructions

    def _resolved(run_context: RunContextWrapper[Any], _agent: BaseAgent) -> Any:
        return instructions(run_context.context)

    return _resolved


SubagentsList = list["type[Agent] | Subagent"]
SubagentsDict = dict[Literal["handoff", "delegate", "auto"], SubagentsList]


def _flatten_subagents(subagents: SubagentsList | SubagentsDict) -> SubagentsList:
    """Normalize the `subagents` class attribute to the flat list the wiring loop expects.

    Accepts either a plain list (each entry bare, or `.handoff`/`.delegate`-wrapped) or a
    `{"handoff": [...], "delegate": [...], "auto": [...]}` dict, where the key supplies the
    mode for any bare entry.
    """
    if not isinstance(subagents, dict):
        return list(subagents)
    flat: SubagentsList = []
    for mode, subs in subagents.items():
        for sub in subs:
            flat.append(sub if mode == "auto" or isinstance(sub, Subagent) else Subagent(sub, mode))
    return flat


class _Mode:
    def __init__(self, mode: Literal["handoff", "delegate"]) -> None:
        self.mode: Literal["handoff", "delegate"] = mode

    def __get__(self, instance: object, owner: type[Agent]) -> Subagent:
        return Subagent(owner, self.mode)


class Agent(BaseAgent):
    """An Agent whose config comes from class attributes instead of __init__ args."""

    handoff = _Mode("handoff")
    delegate = _Mode("delegate")
    model = "gpt-5.4-nano"

    def __init__(self, **kwargs: Any) -> None:
        """Build kwargs from class attributes and wire up any subagents and guardrails."""
        for f in fields(BaseAgent):
            value = getattr(type(self), f.name, MISSING)
            if value is not MISSING:
                kwargs.setdefault(f.name, value)
        handoffs = list(kwargs.get("handoffs", []))
        tools = list(kwargs.get("tools", []))
        for sub in _flatten_subagents(getattr(type(self), "subagents", [])):
            if isinstance(sub, Subagent):
                agent = sub.agent()
                if sub.mode == "handoff":
                    handoffs.append(agent)
                else:
                    tools.append(agent.as_tool(sub.tool_name, sub.tool_description))
            else:
                agent = sub()
                handoffs.append(agent)
                tools.append(agent.as_tool(None, None))
        kwargs["handoffs"] = handoffs
        kwargs["tools"] = tools
        if "instructions" in kwargs:
            kwargs["instructions"] = _adapt_instructions(kwargs["instructions"])
        new_input_guardrails, new_output_guardrails = flatten_agent_guardrails(
            getattr(type(self), "guardrails", [])
        )
        kwargs["input_guardrails"] = [*kwargs.get("input_guardrails", []), *new_input_guardrails]
        kwargs["output_guardrails"] = [
            *kwargs.get("output_guardrails", []),
            *new_output_guardrails,
        ]
        super().__init__(**kwargs)
        self.history: list[TResponseInputItem] = []
        self._last_response_id: str | None = None

    async def run(
        self, message: str, context: Any = None, hooks: RunHooks[Any] | None = None
    ) -> str:
        """Run a turn asynchronously, appending it to the conversation history.

        `context` is available to a single-argument `instructions` callable (and to tools,
        guardrails, etc.) as-is; it is never sent to the model. `hooks` receives lifecycle
        callbacks (`on_agent_start`, `on_tool_end`, etc.) from the underlying SDK's `Runner`;
        it defaults to every built-in `RunHooks` (logging, metrics, tracing, audit) combined.
        """
        turn_input = [*self.history, {"role": "user", "content": message}]
        result = await Runner.run(
            self,
            turn_input,
            context=context,
            hooks=hooks or _default_hooks(),
            run_config=_RUN_CONFIG,
        )
        self.history = result.to_input_list()
        return result.final_output

    async def run_streamed(
        self,
        message: str,
        context: Any = None,
        hooks: RunHooks[Any] | None = None,
        session: ResponsesWebSocketSession | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """Run a turn as a stream of events, appending it to the conversation history.

        Yields the underlying SDK's `StreamEvent`s (`raw_response_event`,
        `run_item_stream_event`, `agent_updated_stream_event`) as they arrive. `context` and
        `hooks` behave as in `run`/`run_sync`. The conversation history is updated only once the
        stream is fully consumed, so a caller that stops iterating early leaves `self.history`
        unchanged.

        Pass a `session` (from `websocket_session()`) to run over a shared, kept-warm OpenAI
        Responses websocket connection. Continuity across turns is then carried server-side via
        `previous_response_id` instead of resending `self.history`, so only the new `message` is
        sent as input.
        """
        if session is not None:
            result = session.run_streamed(
                self,
                message,
                context=context,
                hooks=hooks or _default_hooks(),
                previous_response_id=self._last_response_id,
            )
            async for event in result.stream_events():
                yield event
            self._last_response_id = result.last_response_id
            self.history = result.to_input_list()
            return

        turn_input = [*self.history, {"role": "user", "content": message}]
        result = Runner.run_streamed(
            self,
            turn_input,
            context=context,
            hooks=hooks or _default_hooks(),
            run_config=_RUN_CONFIG,
        )
        async for event in result.stream_events():
            yield event
        self.history = result.to_input_list()

    def run_sync(
        self, message: str, context: Any = None, hooks: RunHooks[Any] | None = None
    ) -> str:
        """Run a turn synchronously, appending it to the conversation history.

        `context` is available to a single-argument `instructions` callable (and to tools,
        guardrails, etc.) as-is; it is never sent to the model. `hooks` receives lifecycle
        callbacks (`on_agent_start`, `on_tool_end`, etc.) from the underlying SDK's `Runner`;
        it defaults to every built-in `RunHooks` (logging, metrics, tracing, audit) combined.
        """
        turn_input = [*self.history, {"role": "user", "content": message}]
        result = Runner.run_sync(
            self,
            turn_input,
            context=context,
            hooks=hooks or _default_hooks(),
            run_config=_RUN_CONFIG,
        )
        self.history = result.to_input_list()
        return result.final_output


@dataclass(frozen=True)
class Subagent:
    """A wired-up subagent, attached as a handoff or a delegate tool."""

    agent: type[Agent]
    mode: Literal["handoff", "delegate"]
    tool_name: str | None = None
    tool_description: str | None = None

    def __call__(
        self, *, tool_name: str | None = None, tool_description: str | None = None
    ) -> Subagent:
        """Return a copy with the tool name/description overridden."""
        return replace(self, tool_name=tool_name, tool_description=tool_description)


__all__ = ["Agent", "Subagent", "websocket_session"]
