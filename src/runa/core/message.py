"""Message and ToolCall: the units exchanged between a Run and a model.

`Message` is communication exchanged with the model: a system, user,
assistant, or tool-result turn, whatever an assistant Message's
`tool_calls` request.

`ToolCall` is an action requested by the model. It begins as that request
(`name`, `arguments`) and accumulates its execution outcome in place over
its lifecycle (`attempts`, `error`, `result`, `effect`) as the Executor
runs it, an approval gate defers it, or a Strategy retries it. Runa does
not split this into separate request/result types: there is one call,
whose state changes over time (see `ToolCall.succeeded`)."""

import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Role(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class EffectStatus(StrEnum):
    """Whether a ToolCall's side effect, if any, is known to have happened.

    A call that raises partway through leaves its effect ambiguous: the
    exception doesn't say whether it fired before or after the underlying
    side effect took hold, so a failed attempt is UNKNOWN, not NONE.
    Blindly retrying an UNKNOWN, non-idempotent call risks repeating that
    effect (architecture.md §13); see `Tool.idempotent` and `RetryStrategy`.
    """

    NONE = "none"
    OBSERVED = "observed"
    UNKNOWN = "unknown"


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    # May legitimately be None even after a successful attempt (a Tool
    # with no meaningful return value), so it must never be read as a
    # proxy for whether execution happened; use `attempts`/`succeeded`.
    result: Any = None
    # Tri-state, not a bool: None means undecided/not applicable, True
    # approved, False denied. Collapsing this to a bool would make
    # "not yet decided" indistinguishable from "denied".
    approved: bool | None = None
    # The current execution failure, if any. None both before the first
    # attempt and after a successful one; only `attempts` tells those apart.
    error: str | None = None
    # Number of execution attempts made so far.
    attempts: int = 0
    # The idempotency semantics of this invocation, resolved from the
    # matching Tool when the call is prepared (see `Executor._call_tool`)
    # so retry logic can read it off the call itself without re-resolving
    # the Tool. Constant for the life of this ToolCall across attempts.
    idempotent: bool = False
    effect: EffectStatus = EffectStatus.NONE

    @property
    def succeeded(self) -> bool:
        """Whether this call has been attempted and succeeded.

        Not `self.result is not None`: a Tool can legitimately return
        `None` as its actual result (a call with no meaningful return
        value), which that check would misread as "never ran." `attempts
        > 0` marks it as attempted; `error is None` distinguishes a
        successful attempt from a failed one still pending a Fail/retry
        decision (see `strategy.py`, `retry.py`).

        Not `completed`: a call that failed for good (exhausted retries,
        non-idempotent and errored once) has finished its lifecycle but
        never succeeded. Callers that mean "still needs running or
        retrying" want `not succeeded`, not a separate `completed` check;
        callers that need to tell "never attempted" apart from "attempted
        and failed" read `attempts` and `error` directly.
        """
        return self.attempts > 0 and self.error is None


@dataclass
class Message:
    role: Role
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str | None = None
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    # Token accounting for a model-generated Message, e.g.
    # {"input_tokens": 512, "output_tokens": 64}. None for a Message that
    # didn't come from a model call, or from a provider that didn't report
    # usage. Providers normalize their vendor-specific usage shape into
    # these two keys, see providers/*.py.
    usage: dict[str, int] | None = None
