"""AsyncProvider: the async counterpart to `Provider` (see `provider.py`).

A separate protocol, not a change to `Provider`: a sync and an async client
for the same vendor API are genuinely different objects, so a Provider is
either one or the other, never both.

`AsyncStreamingProvider` mirrors `StreamingProvider` the same way: an
optional, separate protocol a Provider may additionally satisfy.
"""

import asyncio
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
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


@dataclass
class AsyncRetryingProvider:
    """Wraps an AsyncProvider, retrying `complete()` before giving up.

    The retry wrapper for `Executor`, Runa's canonical execution path (see
    `RetryingProvider` in `provider.py` for the synchronous counterpart,
    used for direct Provider use outside an Agent's own Executor). Same
    retry policy, `await`ed instead of blocking: any exception retried by
    default, up to `max_retries` times, doubling `backoff` seconds each
    attempt, with `is_retryable` as the escape hatch for a specific
    Provider's own exception types. `sleep` defaults to `asyncio.sleep`
    rather than `time.sleep`, so a retry delay doesn't block the event loop.
    """

    provider: AsyncProvider
    max_retries: int = 3
    backoff: float = 1.0
    is_retryable: Callable[[Exception], bool] = lambda exc: True
    sleep: Callable[[float], Any] = field(default=asyncio.sleep, repr=False)

    async def complete(
        self,
        *,
        messages: list[Message],
        tools: list[dict[str, Any]],
        model: str | None,
    ) -> Message:
        attempt = 0
        while True:
            try:
                return await self.provider.complete(
                    messages=messages, tools=tools, model=model
                )
            except Exception as exc:
                attempt += 1
                if attempt > self.max_retries or not self.is_retryable(exc):
                    raise
                await self.sleep(self.backoff * (2 ** (attempt - 1)))


class AsyncStream:
    """The async counterpart to `Stream` (see `provider.py`).

    `async for chunk in stream` for deltas as they arrive; `message` is set
    once the underlying vendor stream is exhausted; read it only after
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
            "AsyncStream exhausted without setting `message`: the "
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
        """Not `async def`: returns an `AsyncStream` immediately; the
        request itself only fires once that AsyncStream is iterated, same
        as `Stream`."""
        ...
