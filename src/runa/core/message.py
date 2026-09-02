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


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    result: Any = None
    approved: bool | None = None
    error: str | None = None
    attempts: int = 0

    @property
    def completed(self) -> bool:
        return self.result is not None


@dataclass
class Message:
    role: Role
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str | None = None
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
