"""AsyncExecutor: the async counterpart to `Executor` (see `executor.py`).

Same Run state machine, same `Strategy` protocol, same Agent hooks — only
*how* actions are carried out differs: model calls go through an
`AsyncProvider`, and independent pending tool calls run concurrently instead
of one at a time.
"""

import asyncio
import inspect
from typing import TYPE_CHECKING

from runa.core import Artifact, EventType, Message, Role, Run, RunStatus, ToolCall
from runa.runtime._shared import seed_run, tool_schemas
from runa.runtime.async_provider import AsyncProvider
from runa.runtime.strategy import (
    Action,
    CallModel,
    CallTool,
    Complete,
    DefaultStrategy,
    Fail,
    Strategy,
)

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

    async def run(self, agent: "Agent", run: Run) -> Run:
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
                await self._apply(agent, run, action)
            except Exception as exc:  # convert into a failed Run, not a crash
                run.fail(error=str(exc))
                break

        if run.is_terminal:
            agent.after_run(run)
            if run.conversation is not None:
                run.conversation.record(run)
        return run

    async def _apply(self, agent: "Agent", run: Run, action: Action) -> None:
        if isinstance(action, CallModel):
            await self._call_model(agent, run)
        elif isinstance(action, CallTool):
            await self._call_tools(agent, run, action.tool_call)
        elif isinstance(action, Complete):
            revised = agent.review(run)
            run.complete(result=action.result if revised is None else revised)
        elif isinstance(action, Fail):
            run.fail(error=action.error)
        else:
            raise TypeError(f"unknown action: {action!r}")

    async def _call_model(self, agent: "Agent", run: Run) -> None:
        run.emit(EventType.MODEL_CALLED)
        schemas = tool_schemas(agent)
        message = await self.provider.complete(
            messages=run.messages, tools=schemas, model=agent.model
        )
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
        run.emit(EventType.TOOL_CALLED, tool=tool_call.name, tool_call_id=tool_call.id)
        tool_call.attempts += 1

        try:
            if inspect.iscoroutinefunction(tool.call):
                result = await tool.call(**tool_call.arguments)
            else:
                result = await asyncio.to_thread(tool.call, **tool_call.arguments)
        except Exception as exc:
            tool_call.error = str(exc)
            run.emit(
                EventType.TOOL_FAILED,
                tool=tool_call.name,
                tool_call_id=tool_call.id,
                error=str(exc),
            )
            return

        tool_call.error = None
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
            EventType.TOOL_COMPLETED, tool=tool_call.name, tool_call_id=tool_call.id
        )
