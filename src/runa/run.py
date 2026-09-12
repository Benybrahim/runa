"""`Run`: the result of `Agent.run()`/`Agent.run_sync()`."""

from dataclasses import dataclass, field
from typing import Any, Literal

from runa._types import Usage
from runa.tracing import Trace

Status = Literal["completed", "error"]


@dataclass
class Run:
    """The outcome of a single `Agent.run()`/`run_sync()` call.

    `output` is the agent's final output, `None` when `status` is `"error"`. `trace` is the
    hierarchical `Trace` (agent/LLM/tool/handoff/guardrail spans) captured for this call, see
    `runa.tracing`; tracing is automatic and needs no configuration, so `trace` always reflects
    what actually happened, never an empty stand-in, except when tracing itself is disabled.
    `usage` is this call's token usage, same value as `Agent.last_usage` after the call.

    `status` is `"error"` when a `RunaError` (a guardrail tripwire, `MaxTurnsExceeded`, a model
    error, ...) stopped the run instead of it reaching a final output; `error` then holds that
    exception's message. `metadata` is reserved for future per-run detail.
    """

    output: Any
    trace: Trace | None
    usage: Usage
    status: Status = "completed"
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


__all__ = ["Run", "Status"]
