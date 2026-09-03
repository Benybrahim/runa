"""AsyncProvider: the async counterpart to `Provider` (see `provider.py`).

A separate protocol, not a change to `Provider` — a sync and an async client
for the same vendor API are genuinely different objects, so a Provider is
either one or the other, never both.
"""

from typing import Any, Protocol

from runa.core import Message


class AsyncProvider(Protocol):
    async def complete(
        self,
        *,
        messages: list[Message],
        tools: list[dict[str, Any]],
        model: str | None,
    ) -> Message: ...
