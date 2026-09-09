"""_core.py: the turn loop (`_run_turns`), run/resume orchestration, and the public `Runner`."""

from __future__ import annotations

import time
from typing import Any

from runa._runner._guardrails import _run_input_guardrails, _run_output_guardrails
from runa._runner._helpers import (
    _agent_tools,
    _model_settings,
    _resolve_instructions,
    _resolve_model,
)
from runa._runner._spans import _close_span, _export, _new_span
from runa._runner._state import RunConfig, RunResult, RunState, gen_trace_id
from runa._runner._streaming import RunResultStreaming
from runa._runner._tool_calls import _run_message_tool_calls, _TurnOutcome
from runa._types import RunContextWrapper, TResponseInputItem
from runa.exceptions import MaxTurnsExceeded, ModelBehaviorError, RunaError
from runa.logging import RunHooks, logger
from runa.session import SessionABC
from runa.tracing._trace import Trace


def _latest_user_text(items: list[TResponseInputItem]) -> str | None:
    """The most recent plain-text user message in `items`, Memory's default search query."""
    for item in reversed(items):
        if item.get("role") == "user" and isinstance(item.get("content"), str):
            return item["content"]
    return None


def _memory_block(matches: list[Any]) -> TResponseInputItem:
    """A small, clearly labeled system message carrying retrieved `MemoryMatch`es."""
    lines = "\n".join(f"- {match.text}" for match in matches)
    return {"role": "system", "content": f"Relevant memories:\n{lines}"}


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

    memory = getattr(agent, "memory", None)
    user_id = getattr(session, "user_id", None) if session is not None else None
    memory_query = _latest_user_text(items)
    if memory is not None and memory_query is not None:
        try:
            memory_matches = await memory.search(memory_query, user_id=user_id)
        except Exception:
            logger.warning("memory retrieval failed for agent %s", agent.name, exc_info=True)
            memory_matches = []
        if memory_matches:
            items.insert(len(items) - 1, _memory_block(memory_matches))

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

    if memory is not None and memory_query is not None:
        try:
            conversation = f"User: {memory_query}\nAssistant: {outcome.final_output}"
            resolved_model = _resolve_model(agent, run_config.model_provider)
            await memory._remember_from_conversation(
                conversation, user_id=user_id, model=resolved_model
            )
        except Exception:
            logger.warning("memory extraction failed for agent %s", agent.name, exc_info=True)

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


__all__ = ["Runner", "_default_hooks", "_resume", "_run_async", "_run_turns"]
