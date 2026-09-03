"""Executor: drives a Strategy against a Run, emitting Events as it acts."""

import inspect
from typing import TYPE_CHECKING

from runa.core import EventType, Message, Role, Run, RunStatus, ToolCall
from runa.runtime._shared import seed_run, tool_schemas
from runa.runtime.provider import Provider
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
    # Agent.run()/.run_later() construct an Executor, so a runtime import here
    # would cycle back through agent.py — this is used for type hints only.
    from runa.agent import Agent


class Executor:
    """Drives a Strategy against a Run.

    Seeds the initial messages, calls the model, executes tools, and applies
    the Strategy's decisions until the Run leaves RUNNING — either because it
    reached a terminal status, or because it paused for background handoff
    or an approval gate (see `background/` and `approval.py`). Calling `run`
    again on a paused Run resumes it from where it left off.

    Agent hooks fire in one fixed order: `before_run` and `plan` once, before
    the first Strategy step; `review` once, when the Strategy decides to
    Complete; `after_run` once the Run reaches a terminal status. Resuming a
    paused Run skips `before_run`/`plan` — they're a start-of-run setup
    phase, not re-run on every resume.

    If `run.conversation` is set, its history is seeded in ahead of this
    Run's own input, and this Run's messages are folded back into it once
    the Run reaches a terminal status — that's what lets a later Run pick
    up the conversation where this one left off (see `Agent.run`).
    """

    def __init__(
        self,
        provider: Provider,
        strategy: Strategy | None = None,
        *,
        max_steps: int = 50,
    ) -> None:
        self.provider = provider
        self.strategy = strategy or DefaultStrategy()
        self.max_steps = max_steps

    def run(self, agent: "Agent", run: Run) -> Run:
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
                self._apply(agent, run, action)
            except Exception as exc:  # convert into a failed Run, not a crash
                run.fail(error=str(exc))
                break

        if run.is_terminal:
            agent.after_run(run)
            if run.conversation is not None:
                run.conversation.record(run)
        return run

    def _apply(self, agent: "Agent", run: Run, action: Action) -> None:
        if isinstance(action, CallModel):
            self._call_model(agent, run)
        elif isinstance(action, CallTool):
            self._call_tool(agent, run, action.tool_call)
        elif isinstance(action, Complete):
            agent.review(run)
            run.complete(result=action.result)
        elif isinstance(action, Fail):
            run.fail(error=action.error)
        else:
            raise TypeError(f"unknown action: {action!r}")

    def _call_model(self, agent: "Agent", run: Run) -> None:
        run.emit(EventType.MODEL_CALLED)
        schemas = tool_schemas(agent)
        message = self.provider.complete(
            messages=run.messages, tools=schemas, model=agent.model
        )
        run.add_message(message)
        run.emit(EventType.MODEL_RESPONDED)

    def _call_tool(self, agent: "Agent", run: Run, tool_call: ToolCall) -> None:
        if (
            tool_call.name in agent.approval_tool_names()
            and tool_call.approved is not True
        ):
            run.require_approval(tool_call.id)
            return

        tool = agent.resolved_tools()[tool_call.name]
        if inspect.iscoroutinefunction(tool.call):
            raise TypeError(
                f"{tool.tool_name()!r} defines an async call() — run this Agent with "
                "AsyncExecutor instead of Executor"
            )
        run.emit(EventType.TOOL_CALLED, tool=tool_call.name, tool_call_id=tool_call.id)
        tool_call.attempts += 1

        try:
            tool_call.result = tool.call(**tool_call.arguments)
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
        run.add_message(
            Message(
                role=Role.TOOL,
                content=str(tool_call.result),
                tool_call_id=tool_call.id,
            )
        )
        run.emit(
            EventType.TOOL_COMPLETED, tool=tool_call.name, tool_call_id=tool_call.id
        )
