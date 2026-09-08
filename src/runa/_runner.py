"""_runner.py: `Runner`, Runa's own agent loop — replaces `agents.Runner`.

One turn: call the model, then either return its text (subject to output guardrails) or execute
whatever tools it called (subject to tool guardrails and `needs_approval`) and loop. A handoff is
just a tool call whose name matches a registered `Handoff`; calling it switches `current_agent` for
the rest of the run. Tracing spans (`runa.tracing.Span`/`Trace`) are emitted directly as the loop
runs — there is no separate SDK trace to adapt from, so this is the one and only tracer.
"""

from __future__ import annotations

import inspect
import json
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Literal

from runa._models import Model, ModelProvider, StreamDelta
from runa._types import ModelSettings, RunContextWrapper, TResponseInputItem, Usage
from runa.exceptions import (
    InputGuardrailTripwireTriggered,
    MaxTurnsExceeded,
    ModelBehaviorError,
    OutputGuardrailTripwireTriggered,
    RunaError,
    ToolInputGuardrailTripwireTriggered,
    ToolOutputGuardrailTripwireTriggered,
)
from runa.guardrail import ToolInputGuardrailContext, ToolInputGuardrailData
from runa.handoff import Handoff
from runa.logging import RunHooks
from runa.session import SessionABC
from runa.tool import FunctionTool
from runa.tracing import config as tracing_config
from runa.tracing._span import Span
from runa.tracing._trace import Trace
from runa.tracing.config import exporters

_DEFAULT_MAX_TURNS = 10


def gen_trace_id() -> str:
    """Generate a fresh, opaque trace id."""
    return uuid.uuid4().hex


def _gen_span_id() -> str:
    return uuid.uuid4().hex


@dataclass
class RunConfig:
    """Per-call configuration for `Runner.run`/`run_sync`/`run_streamed`.

    `workflow_name` names the `Trace` this run produces; `group_id`/`trace_metadata` are recorded
    on it verbatim. `model_provider` resolves an `Agent.model` string to a `Model` — irrelevant
    when `Agent.model` is already a `Model` instance (as Runa's own tests do, to script one).
    """

    model_provider: ModelProvider = field(default_factory=ModelProvider)
    workflow_name: str = "Agent"
    group_id: str | None = None
    trace_metadata: dict[str, Any] | None = None
    max_turns: int = _DEFAULT_MAX_TURNS


@dataclass
class GuardrailResult:
    """A guardrail plus the verdict it returned; carried by a tripwire exception."""

    guardrail: Any
    output: Any


@dataclass
class Interruption:
    """One tool call paused on `needs_approval`, surfaced to the caller to resolve."""

    name: str
    arguments: str
    call_id: str
    tool: FunctionTool
    agent: Any


@dataclass
class RunState:
    """Enough of a paused run to resume it once its `interruptions` are approved or rejected.

    `generated_items` ends with the assistant message that requested the paused calls;
    `ready_results` holds results already computed this turn for calls in that same message that
    *didn't* need approval — they're carried forward rather than re-executed on resume.
    """

    agent: Any
    original_input: list[TResponseInputItem]
    generated_items: list[TResponseInputItem]
    ready_results: list[TResponseInputItem]
    pending: list[Interruption]
    context_wrapper: RunContextWrapper
    trace: Trace
    approvals: dict[str, bool] = field(default_factory=dict)

    def approve(self, interruption: Interruption) -> None:
        """Mark `interruption` approved; its tool runs when the run is resumed."""
        self.approvals[interruption.call_id] = True

    def reject(self, interruption: Interruption) -> None:
        """Mark `interruption` rejected; its tool is skipped when the run is resumed."""
        self.approvals[interruption.call_id] = False


@dataclass
class RunResult:
    """The outcome of one `Runner.run`/`run_sync` call."""

    final_output: Any
    context_wrapper: RunContextWrapper
    trace: Trace
    _original_input: list[TResponseInputItem]
    _generated_items: list[TResponseInputItem]
    interruptions: list[Interruption] = field(default_factory=list)
    _state: RunState | None = None

    def to_input_list(self) -> list[TResponseInputItem]:
        """Return `original_input + generated_items`: the full history after this run."""
        return [*self._original_input, *self._generated_items]

    def to_state(self) -> RunState:
        """Return the `RunState` to resolve `interruptions` against and resume with."""
        assert self._state is not None, "to_state() needs a run that actually paused"
        return self._state


@dataclass
class RawResponsesStreamEvent:
    """A raw, provider-shaped fragment of a streamed response, passed through as-is."""

    data: StreamDelta
    type: Literal["raw_response_event"] = "raw_response_event"


@dataclass
class RunItemStreamEvent:
    """One completed item produced mid-stream: a message, a tool call, a tool's output, ..."""

    name: Literal["message_output_created", "tool_called", "tool_output", "handoff_occured"]
    item: TResponseInputItem
    type: Literal["run_item_stream_event"] = "run_item_stream_event"


@dataclass
class AgentUpdatedStreamEvent:
    """A handoff switched the agent running this turn."""

    new_agent: Any
    type: Literal["agent_updated_stream_event"] = "agent_updated_stream_event"


StreamEvent = RawResponsesStreamEvent | RunItemStreamEvent | AgentUpdatedStreamEvent


def _new_span(
    trace: Trace, parent_id: str | None, name: str, span_type: Any, *, input: Any = None
) -> Span:
    span = Span(
        id=_gen_span_id(),
        trace_id=trace.id,
        parent_id=parent_id,
        name=name,
        type=span_type,
        start_time=time.time(),
    )
    if input is not None and tracing_config.capture_inputs():
        span.input = tracing_config.apply_policy(input, max_bytes=tracing_config.input_limit())
    trace.spans.append(span)
    return span


def _close_span(span: Span, *, error: str | None = None, output: Any = None) -> None:
    span.end_time = time.time()
    if output is not None and tracing_config.capture_outputs():
        max_bytes = (
            tracing_config.tool_result_limit()
            if span.type == "tool"
            else tracing_config.output_limit()
        )
        span.output = tracing_config.apply_policy(output, max_bytes=max_bytes)
    if error is not None:
        span.status = "error"
        span.error = error


def _normalized_handoffs(handoffs: list[Any]) -> dict[str, Handoff]:
    """Map each handoff's tool name to its `Handoff`, wrapping a bare `Agent` if given one."""
    result: dict[str, Handoff] = {}
    for entry in handoffs:
        handoff = entry if isinstance(entry, Handoff) else Handoff.from_agent(entry)
        result[handoff.tool_name] = handoff
    return result


async def _agent_tools(agent: Any) -> list[FunctionTool]:
    """This agent's own `tools`, plus whatever its `mcp_servers` currently list."""
    tools = list(getattr(agent, "tools", []))
    for server in getattr(agent, "mcp_servers", []):
        tools.extend(await server.list_tools())
    return tools


def _find_tool(tools: list[Any], name: str) -> FunctionTool | None:
    for candidate in tools:
        if isinstance(candidate, FunctionTool) and candidate.name == name:
            return candidate
    return None


async def _maybe_await(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value


async def _needs_approval(
    tool: FunctionTool, context_wrapper: RunContextWrapper, args: dict[str, Any], call_id: str
) -> bool:
    if isinstance(tool.needs_approval, bool):
        return tool.needs_approval
    return bool(await _maybe_await(tool.needs_approval(context_wrapper, args, call_id)))


async def _run_input_guardrails(
    agent: Any, context_wrapper: RunContextWrapper, turn_input: Any, trace: Trace, parent_id: str
) -> None:
    for guardrail in agent.input_guardrails:
        span = _new_span(trace, parent_id, guardrail.name or "guardrail", "guardrail")
        result = await guardrail.guardrail_function(context_wrapper, agent, turn_input)
        _close_span(span, error="tripwire triggered" if result.tripwire_triggered else None)
        if result.tripwire_triggered:
            raise InputGuardrailTripwireTriggered(GuardrailResult(guardrail, result))


async def _run_output_guardrails(
    agent: Any, context_wrapper: RunContextWrapper, output: Any, trace: Trace, parent_id: str
) -> None:
    for guardrail in agent.output_guardrails:
        span = _new_span(trace, parent_id, guardrail.name or "guardrail", "guardrail")
        result = await guardrail.guardrail_function(context_wrapper, agent, output)
        _close_span(span, error="tripwire triggered" if result.tripwire_triggered else None)
        if result.tripwire_triggered:
            raise OutputGuardrailTripwireTriggered(GuardrailResult(guardrail, result))


async def _run_tool_input_guardrails(
    tool: FunctionTool, args_json: str, call_id: str, trace: Trace, parent_id: str
) -> None:
    for guardrail in tool.tool_input_guardrails or []:
        span = _new_span(trace, parent_id, guardrail.get_name(), "guardrail")
        data = ToolInputGuardrailData(
            context=ToolInputGuardrailContext(tool_arguments=args_json, call_id=call_id)
        )
        result = await guardrail.guardrail_function(data)
        tripped = result.behavior["type"] == "raise_exception"
        _close_span(span, error="tripwire triggered" if tripped else None)
        if tripped:
            raise ToolInputGuardrailTripwireTriggered(guardrail, result)


async def _run_tool_output_guardrails(
    tool: FunctionTool, args_json: str, call_id: str, output: Any, trace: Trace, parent_id: str
) -> None:
    for guardrail in tool.tool_output_guardrails or []:
        span = _new_span(trace, parent_id, guardrail.get_name(), "guardrail")
        data = ToolInputGuardrailData(
            context=ToolInputGuardrailContext(tool_arguments=args_json, call_id=call_id),
            output=output,
        )
        result = await guardrail.guardrail_function(data)
        tripped = result.behavior["type"] == "raise_exception"
        _close_span(span, error="tripwire triggered" if tripped else None)
        if tripped:
            raise ToolOutputGuardrailTripwireTriggered(guardrail, result)


def _model_settings(agent: Any) -> ModelSettings:
    settings = getattr(agent, "model_settings", None)
    return settings if isinstance(settings, ModelSettings) else ModelSettings()


def _resolve_model(agent: Any, model_provider: ModelProvider) -> Model:
    return (
        agent.model if not isinstance(agent.model, str) else model_provider.get_model(agent.model)
    )


async def _resolve_instructions(agent: Any, context_wrapper: RunContextWrapper) -> str | None:
    """Resolve `agent.instructions`: a string passes through, a callable is called and awaited."""
    instructions = getattr(agent, "instructions", None)
    if not callable(instructions):
        return instructions
    return await _maybe_await(instructions(context_wrapper, agent))


async def _run_tool_call(
    tool: FunctionTool,
    call: dict[str, Any],
    context_wrapper: RunContextWrapper,
    agent: Any,
    hooks: RunHooks[Any],
    trace: Trace,
    parent_id: str,
) -> TResponseInputItem:
    """Run one already-approved tool call end to end: guardrails, invocation, guardrails."""
    call_id = call["id"]
    args_json = call["function"]["arguments"] or "{}"
    span = _new_span(trace, parent_id, tool.name, "tool", input=args_json)
    await hooks.on_tool_start(context_wrapper, agent, tool)
    try:
        await _run_tool_input_guardrails(tool, args_json, call_id, trace, span.id)
        try:
            result = await tool.on_invoke_tool(context_wrapper, args_json, call_id)
            error: str | None = None
        except Exception as exc:  # noqa: BLE001 -- a tool failing is data, not a run-ending error
            result = f"error: {exc}"
            error = str(exc)
        await _run_tool_output_guardrails(tool, args_json, call_id, result, trace, span.id)
    except BaseException:
        _close_span(span, error="tool guardrail tripwire triggered")
        raise
    _close_span(span, error=error, output=result)
    await hooks.on_tool_end(context_wrapper, agent, tool, result)
    return {"role": "tool", "tool_call_id": call_id, "content": str(result)}


@dataclass
class _TurnOutcome:
    final_output: str | None
    generated: list[TResponseInputItem]
    interruptions: list[Interruption]
    ready_results: list[TResponseInputItem]
    current_agent: Any


async def _run_message_tool_calls(
    message: dict[str, Any],
    current_agent: Any,
    context_wrapper: RunContextWrapper,
    hooks: RunHooks[Any],
    trace: Trace,
    parent_id: str,
    approvals: dict[str, bool] | None,
) -> tuple[list[TResponseInputItem], list[Interruption], Any]:
    """Execute (or defer for approval) every tool call in `message`; returns results so far."""
    handoff_map = _normalized_handoffs(getattr(current_agent, "handoffs", []))
    tools = await _agent_tools(current_agent)
    results: list[TResponseInputItem] = []
    interruptions: list[Interruption] = []
    switched_agent: Any = None
    approvals = approvals or {}

    for call in message.get("tool_calls") or []:
        name = call["function"]["name"]
        call_id = call["id"]
        if name in handoff_map:
            handoff = handoff_map[name]
            switched_agent = handoff.agent
            span = _new_span(trace, parent_id, handoff.tool_name, "handoff")
            _close_span(span)
            await hooks.on_handoff(context_wrapper, current_agent, switched_agent)
            results.append(
                {
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": f"Transferred to {switched_agent.name}.",
                }
            )
            continue

        tool = _find_tool(tools, name)
        if tool is None:
            results.append(
                {"role": "tool", "tool_call_id": call_id, "content": f"error: unknown tool {name}"}
            )
            continue

        args_json = call["function"]["arguments"] or "{}"
        args = json.loads(args_json) if args_json else {}
        if await _needs_approval(tool, context_wrapper, args, call_id):
            verdict = approvals.get(call_id)
            if verdict is None:
                interruptions.append(
                    Interruption(
                        name=name,
                        arguments=args_json,
                        call_id=call_id,
                        tool=tool,
                        agent=current_agent,
                    )
                )
                continue
            if verdict is False:
                results.append(
                    {"role": "tool", "tool_call_id": call_id, "content": "rejected by the operator"}
                )
                continue

        results.append(
            await _run_tool_call(
                tool, call, context_wrapper, current_agent, hooks, trace, parent_id
            )
        )

    return results, interruptions, switched_agent


async def _run_turns(
    current_agent: Any,
    items: list[TResponseInputItem],
    context_wrapper: RunContextWrapper,
    hooks: RunHooks[Any],
    run_config: RunConfig,
    trace: Trace,
    agent_span_id: str,
    *,
    max_turns: int,
    pending_resume: tuple[TResponseInputItem, dict[str, bool]] | None = None,
) -> _TurnOutcome:
    generated: list[TResponseInputItem] = []

    if pending_resume is not None:
        last_message, approvals = pending_resume
        results, interruptions, switched = await _run_message_tool_calls(
            last_message, current_agent, context_wrapper, hooks, trace, agent_span_id, approvals
        )
        if interruptions:
            return _TurnOutcome(None, [], interruptions, results, current_agent)
        items.extend(results)
        generated.extend(results)
        if switched is not None:
            current_agent = switched

    for _turn in range(max_turns):
        model = _resolve_model(current_agent, run_config.model_provider)
        llm_span = _new_span(
            trace, agent_span_id, str(current_agent.model), "llm", input=list(items)
        )
        system_instructions = await _resolve_instructions(current_agent, context_wrapper)
        await hooks.on_llm_start(context_wrapper, current_agent, system_instructions, items)
        response = await model.get_response(
            system_instructions,
            items,
            _model_settings(current_agent),
            await _agent_tools(current_agent),
            getattr(current_agent, "output_type", None),
            getattr(current_agent, "handoffs", []),
        )
        context_wrapper.usage.add(response.usage)
        _close_span(llm_span, output={"usage": response.usage.__dict__})
        await hooks.on_llm_end(context_wrapper, current_agent, response)

        if not response.output:
            raise ModelBehaviorError("model returned no output items")
        message = response.output[0]
        items.append(message)
        generated.append(message)

        if not message.get("tool_calls"):
            text = message.get("content") or ""
            await _run_output_guardrails(current_agent, context_wrapper, text, trace, agent_span_id)
            return _TurnOutcome(text, generated, [], [], current_agent)

        results, interruptions, switched = await _run_message_tool_calls(
            message, current_agent, context_wrapper, hooks, trace, agent_span_id, None
        )
        if interruptions:
            return _TurnOutcome(None, generated, interruptions, results, current_agent)

        items.extend(results)
        generated.extend(results)
        if switched is not None:
            current_agent = switched
            await hooks.on_agent_start(context_wrapper, current_agent)

    raise MaxTurnsExceeded(f"max turns ({max_turns}) exceeded")


def _default_hooks() -> RunHooks[Any]:
    from runa.logging import LoggingRunHooks

    return LoggingRunHooks()


async def _run_async(
    agent: Any,
    input: str | list[TResponseInputItem] | RunState,
    *,
    context: Any = None,
    hooks: RunHooks[Any] | None = None,
    run_config: RunConfig | None = None,
    session: SessionABC | None = None,
) -> RunResult:
    run_config = run_config or RunConfig()
    hooks = hooks or _default_hooks()

    if isinstance(input, RunState):
        return await _resume(input, hooks, run_config)

    context_wrapper = RunContextWrapper(context=context)
    trace = Trace(id=gen_trace_id(), name=run_config.workflow_name, start_time=time.time())
    if run_config.group_id is not None or run_config.trace_metadata is not None:
        trace.metadata = {**(run_config.trace_metadata or {}), "group_id": run_config.group_id}

    if session is not None:
        history = await session.get_items()
        new_message = {"role": "user", "content": input} if isinstance(input, str) else None
        items = [*history, new_message] if new_message else [*history, *input]
        original_input: list[TResponseInputItem] = []
    else:
        items = [{"role": "user", "content": input}] if isinstance(input, str) else list(input)
        original_input = items if not isinstance(input, str) else []

    agent_span = _new_span(trace, None, agent.name, "agent")
    await hooks.on_agent_start(context_wrapper, agent)
    try:
        await _run_input_guardrails(agent, context_wrapper, input, trace, agent_span.id)
        outcome = await _run_turns(
            agent,
            items,
            context_wrapper,
            hooks,
            run_config,
            trace,
            agent_span.id,
            max_turns=run_config.max_turns,
        )
    except RunaError as exc:
        _close_span(agent_span, error=str(exc))
        trace.end_time = time.time()
        _export(trace)
        from runa.exceptions import RunErrorDetails

        exc.run_data = RunErrorDetails(
            input=input if isinstance(input, str) else list(input),
            new_items=[],
            raw_responses=[],
            last_agent=agent,
            context_wrapper=context_wrapper,
            input_guardrail_results=[],
            output_guardrail_results=[],
            trace=trace,
        )
        raise

    _close_span(agent_span, error=None, output=outcome.final_output)
    trace.end_time = time.time()

    if outcome.interruptions:
        state = RunState(
            agent=outcome.current_agent,
            original_input=original_input,
            generated_items=[*items[: len(items) - len(outcome.ready_results)]]
            if outcome.ready_results
            else list(items),
            ready_results=outcome.ready_results,
            pending=outcome.interruptions,
            context_wrapper=context_wrapper,
            trace=trace,
        )
        _export(trace)
        return RunResult(
            final_output=None,
            context_wrapper=context_wrapper,
            trace=trace,
            _original_input=original_input,
            _generated_items=outcome.generated,
            interruptions=outcome.interruptions,
            _state=state,
        )

    if session is not None:
        to_persist = [{"role": "user", "content": input}] if isinstance(input, str) else list(input)
        await session.add_items([*to_persist, *outcome.generated])

    await hooks.on_agent_end(context_wrapper, outcome.current_agent, outcome.final_output)
    _export(trace)
    return RunResult(
        final_output=outcome.final_output,
        context_wrapper=context_wrapper,
        trace=trace,
        _original_input=original_input,
        _generated_items=outcome.generated,
    )


async def _resume(state: RunState, hooks: RunHooks[Any], run_config: RunConfig) -> RunResult:
    items = list(state.generated_items)
    agent_span = _new_span(state.trace, None, state.agent.name, "agent")

    pending_message = state.generated_items[-1]
    try:
        outcome = await _run_turns(
            state.agent,
            items,
            state.context_wrapper,
            hooks,
            run_config,
            state.trace,
            agent_span.id,
            max_turns=run_config.max_turns,
            pending_resume=(pending_message, state.approvals),
        )
    except RunaError as exc:
        _close_span(agent_span, error=str(exc))
        state.trace.end_time = time.time()
        _export(state.trace)
        from runa.exceptions import RunErrorDetails

        exc.run_data = RunErrorDetails(
            input=state.original_input,
            new_items=[],
            raw_responses=[],
            last_agent=state.agent,
            context_wrapper=state.context_wrapper,
            input_guardrail_results=[],
            output_guardrail_results=[],
            trace=state.trace,
        )
        raise

    _close_span(agent_span, output=outcome.final_output)
    state.trace.end_time = time.time()

    if outcome.interruptions:
        new_state = RunState(
            agent=outcome.current_agent,
            original_input=state.original_input,
            generated_items=items,
            ready_results=outcome.ready_results,
            pending=outcome.interruptions,
            context_wrapper=state.context_wrapper,
            trace=state.trace,
        )
        _export(state.trace)
        return RunResult(
            final_output=None,
            context_wrapper=state.context_wrapper,
            trace=state.trace,
            _original_input=state.original_input,
            _generated_items=outcome.generated,
            interruptions=outcome.interruptions,
            _state=new_state,
        )

    await hooks.on_agent_end(state.context_wrapper, outcome.current_agent, outcome.final_output)
    _export(state.trace)
    return RunResult(
        final_output=outcome.final_output,
        context_wrapper=state.context_wrapper,
        trace=state.trace,
        _original_input=state.original_input,
        _generated_items=[*state.generated_items[:-1], *outcome.generated],
    )


def _export(trace: Trace) -> None:
    from runa.logging import logger

    for exporter in exporters():
        try:
            exporter.export(trace)
        except Exception:  # noqa: BLE001 -- tracing must never break an agent run
            logger.warning("tracing: exporter %r failed", exporter, exc_info=True)


class RunResultStreaming:
    """What `Runner.run_streamed` returns: an async iterator of `StreamEvent`s.

    `context_wrapper`/`to_input_list()` reflect the run's final state once the iterator has been
    fully consumed — both read the same `items` list and `RunContextWrapper` the streaming loop
    mutates in place as it goes, so there's no separate "final result" object to reconcile with.
    """

    def __init__(
        self,
        agent: Any,
        items: list[TResponseInputItem],
        context_wrapper: RunContextWrapper,
        run_config: RunConfig,
        hooks: RunHooks[Any],
    ) -> None:
        """Store the shared, mutable `items`/`context_wrapper` the streaming loop will update."""
        self._items = items
        self.context_wrapper = context_wrapper
        self._events = _stream_async(agent, items, context_wrapper, run_config, hooks)

    def __aiter__(self) -> AsyncIterator[StreamEvent]:
        """Iterate the `StreamEvent`s this run produces."""
        return self._events

    def to_input_list(self) -> list[TResponseInputItem]:
        """Return the full item list so far: original input plus everything generated."""
        return list(self._items)


async def _stream_async(
    agent: Any,
    items: list[TResponseInputItem],
    context_wrapper: RunContextWrapper,
    run_config: RunConfig,
    hooks: RunHooks[Any],
) -> AsyncIterator[StreamEvent]:
    current_agent = agent

    await hooks.on_agent_start(context_wrapper, current_agent)
    for _turn in range(run_config.max_turns):
        model = _resolve_model(current_agent, run_config.model_provider)
        text_parts: list[str] = []
        tool_calls: dict[int, dict[str, Any]] = {}
        usage = Usage()

        system_instructions = await _resolve_instructions(current_agent, context_wrapper)
        turn_tools = await _agent_tools(current_agent)
        async for delta in model.stream_response(
            system_instructions,
            items,
            _model_settings(current_agent),
            turn_tools,
            getattr(current_agent, "output_type", None),
            getattr(current_agent, "handoffs", []),
        ):
            yield RawResponsesStreamEvent(data=delta)
            if delta.text:
                text_parts.append(delta.text)
            if delta.tool_call_index is not None:
                entry = tool_calls.setdefault(
                    delta.tool_call_index,
                    {"id": None, "type": "function", "function": {"name": None, "arguments": ""}},
                )
                if delta.tool_call_id:
                    entry["id"] = delta.tool_call_id
                if delta.tool_call_name:
                    entry["function"]["name"] = delta.tool_call_name
                if delta.tool_call_arguments:
                    entry["function"]["arguments"] += delta.tool_call_arguments
            if delta.usage is not None:
                usage = delta.usage

        context_wrapper.usage.add(usage)
        message: dict[str, Any] = {
            "role": "assistant",
            "content": "".join(text_parts) or None,
            "tool_calls": [tool_calls[i] for i in sorted(tool_calls)] or None,
        }
        items.append(message)
        yield RunItemStreamEvent(name="message_output_created", item=message)

        if not message["tool_calls"]:
            await hooks.on_agent_end(context_wrapper, current_agent, message["content"] or "")
            return

        handoff_map = _normalized_handoffs(getattr(current_agent, "handoffs", []))
        for call in message["tool_calls"]:
            yield RunItemStreamEvent(name="tool_called", item=call)
            name = call["function"]["name"]
            if name in handoff_map:
                current_agent = handoff_map[name].agent
                yield AgentUpdatedStreamEvent(new_agent=current_agent)
                items.append(
                    {
                        "role": "tool",
                        "tool_call_id": call["id"],
                        "content": f"Transferred to {current_agent.name}.",
                    }
                )
                continue
            tool = _find_tool(turn_tools, name)
            if tool is None:
                items.append(
                    {
                        "role": "tool",
                        "tool_call_id": call["id"],
                        "content": f"error: unknown tool {name}",
                    }
                )
                continue
            args_json = call["function"]["arguments"] or "{}"
            try:
                result = await tool.on_invoke_tool(context_wrapper, args_json, call["id"])
            except Exception as exc:  # noqa: BLE001 -- fed back to the model, not a run-ending error
                result = f"error: {exc}"
            tool_result = {"role": "tool", "tool_call_id": call["id"], "content": str(result)}
            items.append(tool_result)
            yield RunItemStreamEvent(name="tool_output", item=tool_result)

    raise MaxTurnsExceeded(f"max turns ({run_config.max_turns}) exceeded")


class Runner:
    """Runs an `Agent` for one turn: `run`/`run_sync` (final output) or `run_streamed` (events)."""

    @staticmethod
    async def run(
        agent: Any,
        input: str | list[TResponseInputItem] | RunState,
        *,
        context: Any = None,
        hooks: RunHooks[Any] | None = None,
        run_config: RunConfig | None = None,
        session: SessionABC | None = None,
    ) -> RunResult:
        """Run `agent` on `input` (or resume a paused `RunState`) and return the final result."""
        return await _run_async(
            agent, input, context=context, hooks=hooks, run_config=run_config, session=session
        )

    @staticmethod
    def run_sync(
        agent: Any,
        input: str | list[TResponseInputItem] | RunState,
        *,
        context: Any = None,
        hooks: RunHooks[Any] | None = None,
        run_config: RunConfig | None = None,
        session: SessionABC | None = None,
    ) -> RunResult:
        """Synchronous `run`, for callers not already inside an event loop."""
        import asyncio

        return asyncio.run(
            Runner.run(
                agent, input, context=context, hooks=hooks, run_config=run_config, session=session
            )
        )

    @staticmethod
    def run_streamed(
        agent: Any,
        input: str | list[TResponseInputItem],
        *,
        context: Any = None,
        hooks: RunHooks[Any] | None = None,
        run_config: RunConfig | None = None,
    ) -> RunResultStreaming:
        """Run `agent` on `input`, returning a `RunResultStreaming` of `StreamEvent`s."""
        items = [{"role": "user", "content": input}] if isinstance(input, str) else list(input)
        return RunResultStreaming(
            agent,
            items,
            RunContextWrapper(context=context),
            run_config or RunConfig(),
            hooks or _default_hooks(),
        )


__all__ = [
    "AgentUpdatedStreamEvent",
    "GuardrailResult",
    "Interruption",
    "RawResponsesStreamEvent",
    "RunConfig",
    "RunItemStreamEvent",
    "RunResult",
    "RunResultStreaming",
    "RunState",
    "Runner",
    "StreamEvent",
    "gen_trace_id",
]
