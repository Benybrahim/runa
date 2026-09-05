"""Executor: drives a Strategy against a Run, emitting Events as it acts."""

import inspect
import time
import warnings
from collections.abc import Callable
from typing import TYPE_CHECKING

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
from runa.runtime.provider import Provider, StreamChunk, StreamingProvider
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
    # Agent.run()/.run_later() construct an Executor, so a runtime import here
    # would cycle back through agent.py; this is used for type hints only.
    from runa.agent import Agent


class Executor:
    """Drives a Strategy against a Run.

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

    Agent hooks fire in one fixed order: seeding, then `before_run` and
    `plan` once, before the first Strategy step; `review` once, when the
    Strategy decides to Complete, its return value replaces the Strategy's
    draft result unless it returns `None` (manifesto §6's "reflection");
    `after_run` once the Run reaches a terminal status. Resuming a paused
    Run skips seeding/`before_run`/`plan`: they're a start-of-run setup
    phase, not re-run on every resume.

    A bug while seeding the Run (`seed_run`) or in `before_run`/`plan` fails
    the Run with that exception as `Run.error`, same as a bug in the
    Strategy loop itself: `run.start()` moves the Run to RUNNING *before*
    any of the three runs, so leaving an exception there unhandled would
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

    def run(
        self,
        agent: "Agent",
        run: Run,
        *,
        on_chunk: Callable[[StreamChunk], None] | None = None,
    ) -> Run:
        """Drive `run` to completion. See the class docstring for the hook order.

        Pass `on_chunk` to receive `StreamChunk` text deltas as each model
        call streams in, instead of only seeing the whole `Message` once
        it's done. The Run's messages, events, and final state end up
        identical either way; `on_chunk` only changes what's observed while
        a CallModel step is in flight. Requires `self.provider` to satisfy
        `StreamingProvider`; raises `TypeError` otherwise.

        A no-op if `run` is already terminal: there's nothing left to
        drive, so `before_run`/`plan`/`after_run` don't fire again and
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
                    agent.plan(run)
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
                    self._apply(agent, run, action, on_chunk)
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

    def _apply(
        self,
        agent: "Agent",
        run: Run,
        action: Action,
        on_chunk: Callable[[StreamChunk], None] | None,
    ) -> None:
        if isinstance(action, CallModel):
            self._call_model(agent, run, on_chunk)
        elif isinstance(action, CallTool):
            self._call_tool(agent, run, action.tool_call)
        elif isinstance(action, Complete):
            revised = agent.review(run)
            run.complete(result=action.result if revised is None else revised)
        elif isinstance(action, Fail):
            run.fail(error=action.error)
        else:
            raise TypeError(f"unknown action: {action!r}")

    def _call_model(
        self,
        agent: "Agent",
        run: Run,
        on_chunk: Callable[[StreamChunk], None] | None,
    ) -> None:
        run.emit(EventType.MODEL_CALLED, model=agent.model)
        schemas = tool_schemas(agent)
        if on_chunk is None:
            message = self.provider.complete(
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
            for chunk in stream:
                on_chunk(chunk)
            message = stream.drain()
        run.add_message(message)
        run.emit(
            EventType.MODEL_RESPONDED,
            content=message.content,
            tool_call_count=len(message.tool_calls),
            usage=message.usage,
        )

    def _call_tool(self, agent: "Agent", run: Run, tool_call: ToolCall) -> None:
        """Run one tool call.

        If `tool.call()` returns an `Artifact`, it's recorded on the Run via
        `run.add_artifact()` and its `summary()` becomes the tool result the
        model sees; a plain value keeps working exactly as before, via
        `str(result)` (manifesto §10: artifacts are a type of tool result,
        not a separate API).
        """
        if not agent.check_policies(run, tool_call):
            run.emit(
                EventType.POLICY_DENIED,
                tool=tool_call.name,
                tool_call_id=tool_call.id,
            )
            run.fail(error=f"tool call {tool_call.name!r} denied by policy")
            return

        if (
            tool_call.name in agent.approval_tool_names()
            and tool_call.approved is not True
        ):
            run.require_approval(tool_call.id)
            return

        tools = agent.resolved_tools()
        tool = tools.get(tool_call.name)
        if tool is None:
            raise ValueError(
                f"model called unknown tool {tool_call.name!r}, declared "
                f"tools are: {sorted(tools) or '(none)'}"
            )
        if inspect.iscoroutinefunction(tool.call):
            raise TypeError(
                f"{tool.tool_name()!r} defines an async call(): run this Agent with "
                "AsyncExecutor instead of Executor"
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
            tool_call.result = tool.call(**tool_call.arguments)
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
