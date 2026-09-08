"""`Run`: the result of `Agent.run()`/`Agent.run_sync()`."""

from dataclasses import dataclass, field
from typing import Any, Literal

from agents.usage import Usage

from runa.hooks import AuditEvent

Status = Literal["completed", "error"]


@dataclass
class Run:
    """The outcome of a single `Agent.run()`/`run_sync()` call.

    `output` is the agent's final output, `None` when `status` is `"error"`. `trace` is the
    ordered `AuditEvent` log collected for this call — empty if a fully custom `hooks` (one
    with no `AuditRunHooks` in it) was passed to `run`/`run_sync`, since overriding the default
    hooks opts out of the built-in trace the same way it already opts out of logging/metrics.
    `usage` is this call's token usage, same value as `Agent.last_usage` after the call.

    `status` is `"error"` when an `AgentsException` (a guardrail tripwire, `MaxTurnsExceeded`,
    a model error, ...) stopped the run instead of it reaching a final output; `error` then
    holds that exception's message. `metadata` is reserved for future per-run detail.
    """

    output: Any
    trace: list[AuditEvent]
    usage: Usage
    status: Status = "completed"
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


__all__ = ["Run", "Status"]
