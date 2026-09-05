"""Message and ToolCall: the units exchanged between a Run and a model."""

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
    result: Any = None
    approved: bool | None = None
    error: str | None = None
    attempts: int = 0
    idempotent: bool = False
    effect: EffectStatus = EffectStatus.NONE

    @property
    def completed(self) -> bool:
        """Whether this call has been attempted and succeeded.

        Not `self.result is not None`: a Tool can legitimately return
        `None` as its actual result (a call with no meaningful return
        value), which that check would misread as "never ran," leaving the
        Strategy to attempt it again forever. `attempts > 0` marks it as
        attempted; `error is None` distinguishes a successful attempt from
        a failed one still pending a Fail/retry decision (see `strategy.py`,
        `retry.py`).
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
