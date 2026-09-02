"""Strategy: given a Run, decide the next action.

Strategy is a single-method protocol so that "one lifecycle, many
strategies" doesn't drift into a graph/node framework. Prefer Agent hooks
(before_run, plan, review, after_run) for customization; reach for a custom
Strategy only when the loop's shape itself must change.
"""

from dataclasses import dataclass
from typing import Any, Protocol

from runa.core import Role, Run, ToolCall


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


class DefaultStrategy:
    """The plain tool-use loop.

    Call the model, run any tool calls it asks for, feed results back, and
    repeat until the model answers without asking for more tools.
    """

    def step(self, run: Run) -> Action:
        if not run.messages:
            return CallModel()

        last = run.messages[-1]

        if last.role != Role.ASSISTANT:
            return CallModel()

        pending = next((tc for tc in last.tool_calls if not tc.completed), None)
        if pending is not None:
            return CallTool(tool_call=pending)

        return Complete(result=last.content)
