"""Executor: drives a Strategy against a Run, emitting Events as it acts.

Async is Runa's canonical execution model: one `Executor` class, not a
separate `Executor`/`AsyncExecutor` pair. A model call goes through a
`Provider`; independent pending tool calls from the same model turn run
concurrently via `asyncio.gather`, the common case of a model turn
requesting several independent tools at once. A tool call that's already
mid-retry (has its own `error` set) is left for its own `Strategy.step()`
vetting. Approval-gated calls are excluded from the batch; if any remain
blocked once the runnable ones finish, the Run pauses into
AWAITING_APPROVAL.

A `Tool.call` may be a plain function or an `async def`: this Executor
awaits async tools directly and runs sync ones via `asyncio.to_thread` so
they can't block the event loop. `Agent.run_sync()` is the synchronous
adapter over this same Executor (see `agent.py`), not a second runtime.
"""

import asyncio
import inspect
import time
import warnings
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
from runa.runtime._shared import seed_run, tool_schemas, transfer_agent
from runa.runtime.provider import Provider, StreamChunk, StreamingProvider
from runa.runtime.strategy import (
    Action,
    CallModel,
    CallTool,
    Complete,
    DefaultStrategy,
    Fail,
    Strategy,
    last_assistant_message,
)
from runa.tool import DelegatesToAgent, ParentRunAware

if TYPE_CHECKING:
    # Agent.run() constructs an Executor, so a runtime import here would
    # cycle back through agent.py; this is used for type hints only.
    from runa.agent import Agent


class Executor:
    """Drives a Strategy against a Run using a `Provider`.

    Seeds the initial messages, calls the model, executes tools, and applies
    the Strategy's decisions until the Run leaves RUNNING, either because it
    reached a terminal status, or because it paused for background handoff
    or an approval gate (see `background/` and `approval.py`). Calling `run`
    again on a paused Run resumes it from where it left off.

    Checks `run.cancel_requested` once per step, alongside `max_steps`: a
    Run cancelled from another thread via `run.request_cancel()` (e.g. one
    being driven by a `ThreadQueue` job) stops at the next step boundary
    rather than mid-call; see `Run.request_cancel()` for why that flag, and
    not calling `run.cancel()` directly, is the safe way to ask.

    `timeout`, like `max_steps`, is a per-call budget checked at that same
    step boundary, not a preemptive, mid-call deadline. It bounds one
    `run()` call's wall-clock time (from when this call starts driving the
    Run, not from `Run.created_at`), so a Run resumed later after a long
    pause (background handoff, approval) gets a fresh budget rather than
    inheriting elapsed wait time. `None` (the default) means no timeout.

    Agent hooks fire in one fixed order: seeding, then `before_run` once,
    before the first Strategy step; `after_run` once the Run reaches a
    terminal status. Resuming a paused Run skips seeding/`before_run`:
    they're a start-of-run setup phase, not re-run on every resume.

    A bug while seeding the Run (`seed_run`) or in `before_run` fails
    the Run with that exception as `Run.error`, same as a bug in the
    Strategy loop itself: `run.start()` moves the Run to RUNNING *before*
    either one runs, so leaving an exception there unhandled would
    strand the Run at RUNNING forever instead of a terminal status,
    indistinguishable from one still genuinely in progress, and, for a Run
    driven from a background thread (`run_later()` on a `ThreadQueue`/
    `SQLiteQueue`), an exception that isn't caught here would otherwise
    vanish into the thread pool with nothing to observe it. `after_run` runs
    after the Run already reached its real terminal status (COMPLETED/
    FAILED/CANCELLED), so a bug there can't be turned into a Run failure
    without falsifying that outcome; it's instead surfaced as a
    `RuntimeWarning` and otherwise ignored, the same treatment
    `instrument()` gives a raising subscriber.

    If `run.conversation` is set, its history is seeded in ahead of this
    Run's own input, and this Run's messages are folded back into it once
    the Run reaches a terminal status; that's what lets a later Run pick
    up the conversation where this one left off (see `Agent.run`).
    """

    def __init__(
        self,
        provider: Provider,
        strategy: Strategy | None = None,
        *,
        max_steps: int = 50,
        timeout: float | None = None,
    ) -> None:
        self.provider = provider
        self.strategy = strategy or DefaultStrategy()
        self.max_steps = max_steps
        self.timeout = timeout

    async def run(
        self,
        agent: "Agent",
        run: Run,
        *,
        on_chunk: Callable[[StreamChunk], Any | Awaitable[Any]] | None = None,
    ) -> Run:
        """Drive `run` to completion. See the class docstring for the hook order.

        Pass `on_chunk` to receive `StreamChunk` text deltas as each model
        call streams in, instead of only seeing the whole `Message` once
        it's done. The Run's messages, events, and final state end up
        identical either way; `on_chunk` only changes what's observed while
        a CallModel step is in flight. May itself be `async def`; a plain
        callable works too, and its return value (if any) is ignored.
        Requires `self.provider` to satisfy `StreamingProvider`; raises
        `TypeError` otherwise.

        A no-op if `run` is already terminal: there's nothing left to
        drive, so `before_run`/`after_run` don't fire again and
        `run.conversation` isn't re-recorded. Without this check, calling
        `run()` a second time on an already-completed Run would silently
        re-invoke `after_run` (see `Run.is_terminal`).

        Raises `RunAlreadyDriving` if another Executor is already driving
        this same Run object; see `Run.begin_driving()`.
        """
        if run.is_terminal:
            return run

        run.begin_driving()
        try:
            if run.status in (RunStatus.CREATED, RunStatus.QUEUED):
                run.start()
                try:
                    seed_run(agent, run)
                    agent.before_run(run)
                except Exception as exc:  # same guarantee as the step loop below
                    run.fail(error=str(exc))
            elif run.status in (RunStatus.PAUSED, RunStatus.AWAITING_APPROVAL):
                run.resume()

            deadline = None if self.timeout is None else time.monotonic() + self.timeout

            steps = 0
            while run.status == RunStatus.RUNNING:
                if run.cancel_requested:
                    run.cancel()
                    break
                if steps >= self.max_steps:
                    run.fail(error=f"exceeded max_steps ({self.max_steps})")
                    break
                if deadline is not None and time.monotonic() >= deadline:
                    run.fail(error=f"exceeded timeout ({self.timeout}s)")
                    break
                steps += 1

                try:
                    action = self.strategy.step(run)
                    agent = await self._apply(agent, run, action, on_chunk)
                except Exception as exc:  # convert into a failed Run, not a crash
                    run.fail(error=str(exc))
                    break

            if run.is_terminal:
                try:
                    agent.after_run(run)
                except Exception as exc:  # Run already terminal; don't falsify it
                    warnings.warn(
                        f"after_run raised {exc!r}, ignored: Run {run.id} "
                        f"already reached a terminal status "
                        f"({run.status.value})",
                        RuntimeWarning,
                        stacklevel=2,
                    )
                if run.conversation is not None:
                    run.conversation.record(run)
        finally:
            run.end_driving()
        return run

    async def _apply(
        self,
        agent: "Agent",
        run: Run,
        action: Action,
        on_chunk: Callable[[StreamChunk], Any] | None,
    ) -> "Agent":
        """Apply one Strategy decision, returning the Agent driving `run` next.

        Always `agent` unchanged, except a `CallTool` batch that resolves to
        a `transfer=true` delegation: see `_call_tools`/`transfer_agent`.
        """
        if isinstance(action, CallModel):
            await self._call_model(agent, run, on_chunk)
        elif isinstance(action, CallTool):
            return await self._call_tools(agent, run, action.tool_call)
        elif isinstance(action, Complete):
            run.complete(result=action.result)
        elif isinstance(action, Fail):
            run.fail(error=action.error)
        else:
            raise TypeError(f"unknown action: {action!r}")
        return agent

    async def _call_model(
        self,
        agent: "Agent",
        run: Run,
        on_chunk: Callable[[StreamChunk], Any] | None,
    ) -> None:
        run.emit(EventType.MODEL_CALLED, model=agent.model)
        schemas = tool_schemas(agent)
        if on_chunk is None:
            message = await self.provider.complete(
                messages=run.messages, tools=schemas, model=agent.model
            )
        else:
            if not isinstance(self.provider, StreamingProvider):
                raise TypeError(
                    f"{type(self.provider).__name__} does not implement "
                    "StreamingProvider.stream(): on_chunk requires a "
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
        run.emit(
            EventType.MODEL_RESPONDED,
            content=message.content,
            tool_call_count=len(message.tool_calls),
            usage=message.usage,
        )

    async def _call_tools(
        self, agent: "Agent", run: Run, named_tool_call: ToolCall
    ) -> "Agent":
        """Run `named_tool_call` plus any fresh sibling pending calls, concurrently.

        Returns the Agent driving `run` next: `agent` unchanged, unless the
        turn's sole candidate is a `transfer=true` delegation.

        `named_tool_call` is whatever the Strategy explicitly vetted this
        step (honoring e.g. RetryStrategy's per-call attempt gating). A
        sibling only joins the batch if it's never been attempted: a
        sibling already mid-retry gets its own vetting on a later step.

        Siblings come from the turn's assistant message via
        `last_assistant_message`, not `run.messages[-1]` directly: once any
        sibling in this turn has already executed (e.g. one batch ran, an
        approval gate paused the rest, and the run was then resumed),
        `run.messages[-1]` is that sibling's TOOL-role result message, not
        the assistant message the still-pending calls actually live on. See
        `last_assistant_message`'s docstring.

        A `transfer=true` call can't compose with concurrent siblings (which
        agent's declared tools would they even belong to once control has
        moved?), so it's only honored when it's the turn's only candidate;
        otherwise the run fails with a clear error rather than running
        anything concurrently.
        """
        # named_tool_call came from this same lookup, so it's never None here.
        last_assistant = last_assistant_message(run)
        assert last_assistant is not None
        pending = [tc for tc in last_assistant.tool_calls if not tc.completed]
        candidates = [tc for tc in pending if tc is named_tool_call or tc.error is None]

        tools = agent.resolved_tools()
        transferring = [
            tc
            for tc in candidates
            if isinstance(tools.get(tc.name), DelegatesToAgent)
            and tc.arguments.get("transfer")
        ]
        if transferring and len(candidates) > 1:
            run.fail(
                error=(
                    "cannot transfer control while other tool calls are "
                    "pending in the same turn"
                )
            )
            return agent

        approval_names = agent.approval_tool_names()
        runnable: list[ToolCall] = []
        blocked: list[ToolCall] = []
        for tool_call in candidates:
            if not agent.check_policies(run, tool_call):
                run.emit(
                    EventType.POLICY_DENIED,
                    tool=tool_call.name,
                    tool_call_id=tool_call.id,
                )
                run.fail(error=f"tool call {tool_call.name!r} denied by policy")
                return agent
            if tool_call.name in approval_names and tool_call.approved is not True:
                blocked.append(tool_call)
            else:
                runnable.append(tool_call)

        if transferring:
            tool_call = transferring[0]
            if tool_call.name in approval_names and tool_call.approved is not True:
                run.require_approval(tool_call.id)
                return agent
            delegation = tools[tool_call.name]
            assert isinstance(delegation, DelegatesToAgent)
            return transfer_agent(agent, run, delegation, tool_call)

        if runnable:
            await asyncio.gather(*(self._call_tool(agent, run, tc) for tc in runnable))

        if blocked and run.status == RunStatus.RUNNING:
            run.require_approval(blocked[0].id)
        return agent

    async def _call_tool(self, agent: "Agent", run: Run, tool_call: ToolCall) -> None:
        """Run one tool call.

        If `tool.call()` returns an `Artifact`, it's recorded on the Run via
        `run.add_artifact()` and its `summary()` becomes the tool result the
        model sees; a plain value keeps working exactly as before, via
        `str(result)` (manifesto §10: artifacts are a type of tool result,
        not a separate API).
        """
        tools = agent.resolved_tools()
        tool = tools.get(tool_call.name)
        if tool is None:
            raise ValueError(
                f"model called unknown tool {tool_call.name!r}, declared "
                f"tools are: {sorted(tools) or '(none)'}"
            )
        tool_call.idempotent = tool.idempotent
        if isinstance(tool, ParentRunAware):
            tool.bind_parent_run_id(run.id)
        run.emit(
            EventType.TOOL_CALLED,
            tool=tool_call.name,
            tool_call_id=tool_call.id,
            arguments=tool_call.arguments,
        )
        tool_call.attempts += 1

        try:
            if inspect.iscoroutinefunction(tool.call):
                result = await tool.call(**tool_call.arguments)
            else:
                result = await asyncio.to_thread(tool.call, **tool_call.arguments)
        except Exception as exc:
            # The exception doesn't say whether the underlying side effect
            # fired before it was raised, so the effect is UNKNOWN, not
            # NONE. See EffectStatus and RetryStrategy.
            tool_call.error = str(exc)
            tool_call.effect = EffectStatus.UNKNOWN
            run.emit(
                EventType.TOOL_FAILED,
                tool=tool_call.name,
                tool_call_id=tool_call.id,
                arguments=tool_call.arguments,
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
            # `content`, not the raw `tool_call.result`: a Tool may return
            # an arbitrary object (e.g. an Artifact), which Event.data must
            # stay JSON-serializable for (persistence, webhook export);
            # `content` is the same already-stringified/summarized value
            # the model itself was given.
            result=content,
            effect=EffectStatus.OBSERVED.value,
        )
