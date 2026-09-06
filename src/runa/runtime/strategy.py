"""Strategy: given a Run, decide the next action.

Every Runa Agent uses the same ReAct-style control loop: observe the Run's
accumulated state, decide an action, execute it, observe the result, and
repeat until the Run completes. `DefaultStrategy` below is that loop.
Runa does not ask applications to choose between a planner, an
orchestrator, a reflection loop, or ReAct: those are theories of agent
behavior, and Runa standardizes execution, not intelligence (RUNA.md §9).

Strategy is a single-method protocol so that "one lifecycle, many
strategies" doesn't drift into a graph/node framework. Prefer Agent hooks
(before_run, after_run) for customization; reach for a custom Strategy
only when the loop's shape itself must change, e.g. `Executor(strategy=
CustomStrategy())`. This is an escape hatch, not a normal Agent
configuration knob: `Agent` has no `strategy` field.
"""

from dataclasses import dataclass
from typing import Any, Protocol

from runa.core import Message, Role, Run, ToolCall


@dataclass
class CallModel:
    """Ask the provider for the next model response."""


@dataclass
class CallTool:
    """Execute a pending tool call."""

    tool_call: ToolCall


@dataclass
class Complete:
    """Finish the run successfully."""

    result: Any = None


@dataclass
class Fail:
    """Finish the run with a failure."""

    error: str


Action = CallModel | CallTool | Complete | Fail


class Strategy(Protocol):
    def step(self, run: Run) -> Action: ...


def last_assistant_message(run: Run) -> Message | None:
    """The most recent assistant message, wherever it sits in `run.messages`.

    Not necessarily `run.messages[-1]`: once any of a turn's tool_calls have
    been executed, their TOOL-role result messages get appended after it. A
    turn with more than one tool_call needs this to keep finding the turn's
    still-pending calls after the first result comes back: using
    `run.messages[-1]` directly would see a TOOL message where an ASSISTANT
    one was expected and wrongly conclude the turn has no pending work left,
    calling the model again mid-turn and silently abandoning the rest of the
    batch (`Executor._call_tools` makes the same lookup, for the same
    reason).
    """
    return next((m for m in reversed(run.messages) if m.role == Role.ASSISTANT), None)


class DefaultStrategy:
    """The universal ReAct-style loop: Runa's one control loop, not a
    default among several.

    Call the model (Reason), run any tool calls it asks for (Act), feed
    results back (Observe), and repeat until the model answers without
    asking for more tools (Finish). Fails the run immediately if a tool
    call errors, no retry policy of its own; see `RetryStrategy` for one.
    """

    def step(self, run: Run) -> Action:
        last_assistant = last_assistant_message(run)
        if last_assistant is None:
            return CallModel()

        pending = next(
            (tc for tc in last_assistant.tool_calls if not tc.succeeded), None
        )
        if pending is not None:
            if pending.error is not None:
                return Fail(error=pending.error)
            return CallTool(tool_call=pending)

        if run.messages[-1] is last_assistant:
            return Complete(result=last_assistant.content)

        return CallModel()
