"""AsyncProvider: the async counterpart to `Provider` (see `provider.py`).

A separate protocol, not a change to `Provider` — a sync and an async client
for the same vendor API are genuinely different objects, so a Provider is
either one or the other, never both.

`AsyncStreamingProvider` mirrors `StreamingProvider` the same way: an
optional, separate protocol a Provider may additionally satisfy.
"""

from collections.abc import AsyncIterator
from typing import Any, Protocol, runtime_checkable

from runa.core import Message
from runa.runtime.provider import StreamChunk


class AsyncProvider(Protocol):
    async def complete(
        self,
        *,
        messages: list[Message],
        tools: list[dict[str, Any]],
        model: str | None,
    ) -> Message: ...


class AsyncStream:
    """The async counterpart to `Stream` (see `provider.py`).

    `async for chunk in stream` for deltas as they arrive; `message` is set
    once the underlying vendor stream is exhausted — read it only after
    the iterator is exhausted (`drain()` does both in one call).
    """

    def __init__(self, chunks: AsyncIterator[StreamChunk]) -> None:
        self._chunks = chunks
        self.message: Message | None = None

    def __aiter__(self) -> AsyncIterator[StreamChunk]:
        return self._chunks

    async def drain(self) -> Message:
        """Consume any remaining chunks and return the final Message."""
        async for _ in self:
            pass
        assert self.message is not None, (
            "AsyncStream exhausted without setting `message` — the "
            "AsyncStreamingProvider that built it has a bug"
        )
        return self.message


@runtime_checkable
class AsyncStreamingProvider(Protocol):
    def stream(
        self,
        *,
        messages: list[Message],
        tools: list[dict[str, Any]],
        model: str | None,
    ) -> AsyncStream:
        """Not `async def` — returns an `AsyncStream` immediately; the
        request itself only fires once that AsyncStream is iterated, same
        as `Stream`."""
        ...
