"""_types.py: the provider-neutral request/response shapes Runa's own runtime is built on.

No OpenAI (or Anthropic) SDK type leaks past `_models.py` — everywhere else in Runa speaks these
types instead: a plain dict for one turn of conversation, a token-usage tally, and per-call model
settings. `_runner.py` builds and consumes these; each `Model` implementation translates them to
and from whatever shape its own provider's wire format actually wants.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

TResponseInputItem = dict[str, Any]
"""One turn of conversation history: a `{"role": ..., "content": ...}` message, a tool call, or a
tool result. Plain JSON, never a provider SDK type — an output item becomes tomorrow's input item
once appended to history, so this one shape serves both directions.
"""

TResponseOutputItem = TResponseInputItem
"""What a model call produces, before it's appended to history — the same shape as
`TResponseInputItem`; see that alias for why one shape covers both.
"""

TResponseStreamEvent = dict[str, Any]
"""One raw provider streaming event, passed through to callers as-is via
`RawResponsesStreamEvent.data`. Opaque to Runa itself: each `Model` decides what to put in it.
"""

ToolChoice = Literal["auto", "required", "none"] | str | None
"""`"auto"`/`"required"`/`"none"`, a specific tool name to force, or `None` for the provider's
default.
"""


@dataclass
class InputTokensDetails:
    """A breakdown of `Usage.input_tokens` into cached and cache-write tokens."""

    cached_tokens: int = 0
    cache_write_tokens: int = 0


@dataclass
class OutputTokensDetails:
    """A breakdown of `Usage.output_tokens` into reasoning tokens."""

    reasoning_tokens: int = 0


@dataclass
class Usage:
    """Token usage for one or more model calls.

    `Agent.run`/`run_sync` accumulate every call's `Usage` into `Agent.usage` via `.add()`, and
    record the latest one on `Agent.last_usage`.
    """

    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    input_tokens_details: InputTokensDetails = field(default_factory=InputTokensDetails)
    output_tokens_details: OutputTokensDetails = field(default_factory=OutputTokensDetails)

    def add(self, other: Usage) -> None:
        """Accumulate `other`'s counts into this `Usage`, in place."""
        self.requests += other.requests
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.total_tokens += other.total_tokens
        self.input_tokens_details.cached_tokens += other.input_tokens_details.cached_tokens
        self.input_tokens_details.cache_write_tokens += (
            other.input_tokens_details.cache_write_tokens
        )
        self.output_tokens_details.reasoning_tokens += other.output_tokens_details.reasoning_tokens


@dataclass
class Reasoning:
    """A reasoning-model's effort/summary settings, for providers that support them."""

    effort: Literal["low", "medium", "high"] | None = None
    summary: Literal["auto", "concise", "detailed"] | None = None


@dataclass
class ModelSettings:
    """Per-call model parameters; a `Model` implementation uses whichever of these its API takes."""

    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
    tool_choice: ToolChoice = None
    parallel_tool_calls: bool | None = None
    reasoning: Reasoning | None = None


@dataclass
class ModelResponse:
    """What a `Model.get_response()` call returns: the model's output items, plus usage."""

    output: list[TResponseOutputItem]
    usage: Usage
    response_id: str | None = None


@dataclass
class RunContextWrapper[TContext]:
    """Wraps the `context` object passed to `Agent.run()`/`run_sync()`, plus usage-so-far.

    `context` is never sent to the model; it's how tools, guardrails, `needs_approval`, and a
    single-argument `instructions` callable receive whatever the caller passed to `run`/`run_sync`.
    """

    context: TContext = None  # pyright: ignore[reportAssignmentType]
    usage: Usage = field(default_factory=Usage)


__all__ = [
    "InputTokensDetails",
    "ModelResponse",
    "ModelSettings",
    "OutputTokensDetails",
    "Reasoning",
    "RunContextWrapper",
    "TResponseInputItem",
    "TResponseOutputItem",
    "TResponseStreamEvent",
    "ToolChoice",
    "Usage",
]
