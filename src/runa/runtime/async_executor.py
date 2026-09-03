"""AsyncExecutor: the async counterpart to `Executor` (see `executor.py`).

Same Run state machine, same `Strategy` protocol, same Agent hooks — only
*how* actions are carried out differs: model calls go through an
`AsyncProvider`, and independent pending tool calls run concurrently instead
of one at a time.
"""

import asyncio
import inspect
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from runa.core import (
    Artifact,
    EffectStatus,
    EventType,
    Message,
    Role,
    Run,
    RunStatus,
    ToolCall,
)
from runa.runtime._shared import seed_run, tool_schemas
from runa.runtime.async_provider import AsyncProvider, AsyncStreamingProvider
from runa.runtime.provider import StreamChunk
from runa.runtime.strategy import (
    Action,
    CallModel,
    CallTool,
    Complete,
    DefaultStrategy,
    Fail,
    Strategy,
)
from runa.tool import ParentRunAware

if TYPE_CHECKING:
    # Agent.run_async() constructs an AsyncExecutor, so a runtime import here
    # would cycle back through agent.py — this is used for type hints only.
    from runa.agent import Agent


class AsyncExecutor:
    """Drives a Strategy against a Run using an `AsyncProvider`.

    Behaves exactly like `Executor`, with one difference: when a Strategy
    step asks to call a tool, this Executor also gathers up any *other*
    pending, never-attempted tool call from the same assistant message and
    runs all of them concurrently via `asyncio.gather` — the common case of
    a model turn requesting several independent tools at once. A tool call
    that's already mid-retry (has its own `error` set) is left for its own
    `Strategy.step()` vetting, same as in `Executor`. Approval-gated calls
    are excluded from the batch; if any remain blocked once the runnable
    ones finish, the Run pauses into AWAITING_APPROVAL exactly as it would
    with `Executor`.

    A `Tool.call` may be a plain function or an `async def` — this Executor
    awaits async tools directly and runs sync ones via `asyncio.to_thread`
    so they can't block the event loop. `Executor` (the sync one) rejects an
    async tool outright rather than silently mishandling it.
    """

    def __init__(
        self,
        provider: AsyncProvider,
        strategy: Strategy | None = None,
        *,
        max_steps: int = 50,
    ) -> None:
        self.provider = provider
        self.strategy = strategy or DefaultStrategy()
        self.max_steps = max_steps

    async def run(
        self,
        agent: "Agent",
        run: Run,
        *,
        on_chunk: Callable[[StreamChunk], Any | Awaitable[Any]] | None = None,
    ) -> Run:
        """Drive `run` to completion. See `Executor.run` for `on_chunk` — same
        contract here, except `on_chunk` may itself be `async def`; a plain
        callable works too, and its return value (if any) is ignored.
        Requires `self.provider` to satisfy `AsyncStreamingProvider`; raises
        `TypeError` otherwise.
        """
        if run.status in (RunStatus.CREATED, RunStatus.QUEUED):
            seed_run(agent, run)
            run.start()
            agent.before_run(run)
            agent.plan(run)
        elif run.status in (RunStatus.PAUSED, RunStatus.AWAITING_APPROVAL):
            run.resume()

        steps = 0
        while run.status == RunStatus.RUNNING:
            if steps >= self.max_steps:
                run.fail(error=f"exceeded max_steps ({self.max_steps})")
                break
            steps += 1

            try:
                action = self.strategy.step(run)
                await self._apply(agent, run, action, on_chunk)
            except Exception as exc:  # convert into a failed Run, not a crash
                run.fail(error=str(exc))
                break

        if run.is_terminal:
            agent.after_run(run)
            if run.conversation is not None:
                run.conversation.record(run)
        return run

    async def _apply(
        self,
        agent: "Agent",
        run: Run,
        action: Action,
        on_chunk: Callable[[StreamChunk], Any] | None,
    ) -> None:
        if isinstance(action, CallModel):
            await self._call_model(agent, run, on_chunk)
        elif isinstance(action, CallTool):
            await self._call_tools(agent, run, action.tool_call)
        elif isinstance(action, Complete):
            revised = agent.review(run)
            run.complete(result=action.result if revised is None else revised)
        elif isinstance(action, Fail):
            run.fail(error=action.error)
        else:
            raise TypeError(f"unknown action: {action!r}")

    async def _call_model(
        self,
        agent: "Agent",
        run: Run,
        on_chunk: Callable[[StreamChunk], Any] | None,
    ) -> None:
        run.emit(EventType.MODEL_CALLED)
        schemas = tool_schemas(agent)
        if on_chunk is None:
            message = await self.provider.complete(
                messages=run.messages, tools=schemas, model=agent.model
            )
        else:
            if not isinstance(self.provider, AsyncStreamingProvider):
                raise TypeError(
                    f"{type(self.provider).__name__} does not implement "
                    "AsyncStreamingProvider.stream() — on_chunk requires a "
                    "streaming-capable Provider"
                )
            stream = self.provider.stream(
                messages=run.messages, tools=schemas, model=agent.model
            )
            async for chunk in stream:
                result = on_chunk(chunk)
                if inspect.isawaitable(result):
                    await result
            message = await stream.drain()
        run.add_message(message)
        run.emit(EventType.MODEL_RESPONDED)

    async def _call_tools(
        self, agent: "Agent", run: Run, named_tool_call: ToolCall
    ) -> None:
        """Run `named_tool_call` plus any fresh sibling pending calls, concurrently.

        `named_tool_call` is whatever the Strategy explicitly vetted this
        step (honoring e.g. RetryStrategy's per-call attempt gating). A
        sibling only joins the batch if it's never been attempted — a
        sibling already mid-retry gets its own vetting on a later step.
        """
        pending = [tc for tc in run.messages[-1].tool_calls if not tc.completed]
        candidates = [tc for tc in pending if tc is named_tool_call or tc.error is None]

        approval_names = agent.approval_tool_names()
        runnable: list[ToolCall] = []
        blocked: list[ToolCall] = []
        for tool_call in candidates:
            if tool_call.name in approval_names and tool_call.approved is not True:
                blocked.append(tool_call)
            else:
                runnable.append(tool_call)

        if runnable:
            await asyncio.gather(*(self._call_tool(agent, run, tc) for tc in runnable))

        if blocked and run.status == RunStatus.RUNNING:
            run.require_approval(blocked[0].id)

    async def _call_tool(self, agent: "Agent", run: Run, tool_call: ToolCall) -> None:
        """Run one tool call — see `Executor._call_tool` for the Artifact dispatch."""
        tool = agent.resolved_tools()[tool_call.name]
        tool_call.idempotent = tool.idempotent
        if isinstance(tool, ParentRunAware):
            tool.bind_parent_run_id(run.id)
        run.emit(EventType.TOOL_CALLED, tool=tool_call.name, tool_call_id=tool_call.id)
        tool_call.attempts += 1

        try:
            if inspect.iscoroutinefunction(tool.call):
                result = await tool.call(**tool_call.arguments)
            else:
                result = await asyncio.to_thread(tool.call, **tool_call.arguments)
        except Exception as exc:
            # The exception doesn't say whether the underlying side effect
            # fired before it was raised, so the effect is UNKNOWN, not
            # NONE — see EffectStatus and RetryStrategy.
            tool_call.error = str(exc)
            tool_call.effect = EffectStatus.UNKNOWN
            run.emit(
                EventType.TOOL_FAILED,
                tool=tool_call.name,
                tool_call_id=tool_call.id,
                error=str(exc),
                effect=EffectStatus.UNKNOWN.value,
            )
            return

        tool_call.error = None
        tool_call.effect = EffectStatus.OBSERVED
        tool_call.result = result
        if isinstance(tool_call.result, Artifact):
            run.add_artifact(tool_call.result)
            content = tool_call.result.summary()
        else:
            content = str(tool_call.result)
        run.add_message(
            Message(role=Role.TOOL, content=content, tool_call_id=tool_call.id)
        )
        run.emit(
            EventType.TOOL_COMPLETED,
            tool=tool_call.name,
            tool_call_id=tool_call.id,
            effect=EffectStatus.OBSERVED.value,
        )
