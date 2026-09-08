"""_state.py: per-call config, paused/finished-run data, and stream event types."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

from runa._models import ModelProvider, StreamDelta
from runa._types import RunContextWrapper, TResponseInputItem
from runa.tool import FunctionTool
from runa.tracing._trace import Trace

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


__all__ = [
    "AgentUpdatedStreamEvent",
    "GuardrailResult",
    "Interruption",
    "RawResponsesStreamEvent",
    "RunConfig",
    "RunItemStreamEvent",
    "RunResult",
    "RunState",
    "StreamEvent",
    "gen_trace_id",
]
