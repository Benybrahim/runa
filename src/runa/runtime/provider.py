"""Provider: the contract between the runtime and a specific model API.

Concrete adapters live in `providers/` and translate between this contract
and a vendor's wire format. The runtime depends only on this protocol, never
on a specific vendor.

`StreamingProvider` is a separate, optional protocol, not a second method
tacked onto `Provider` — a Provider that only implements `complete()` still
satisfies `Provider` on its own (every existing `FakeProvider` in tests
included); one that also implements `stream()` additionally satisfies
`StreamingProvider`, structurally, with no base class to opt into.
`Executor.run(..., on_chunk=...)` is what actually calls `stream()` — see
`runtime/executor.py`.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from runa.core import Message


class Provider(Protocol):
    def complete(
        self,
        *,
        messages: list[Message],
        tools: list[dict[str, Any]],
        model: str | None,
    ) -> Message: ...


@dataclass
class StreamChunk:
    """One incremental piece of a streamed model response — a text delta."""

    delta: str


class Stream:
    """What `StreamingProvider.stream()` returns.

    Iterate for `StreamChunk`s as they arrive. `message` holds the same
    `Message` `complete()` would have returned for the same call — a
    concrete Provider's `stream()` sets it once its underlying vendor
    stream is exhausted, so read it only after the iterator is exhausted
    (`drain()` does both in one call).
    """

    def __init__(self, chunks: Iterator[StreamChunk]) -> None:
        self._chunks = chunks
        self.message: Message | None = None

    def __iter__(self) -> Iterator[StreamChunk]:
        return self._chunks

    def drain(self) -> Message:
        """Consume any remaining chunks and return the final Message."""
        for _ in self:
            pass
        assert self.message is not None, (
            "Stream exhausted without setting `message` — the "
            "StreamingProvider that built it has a bug"
        )
        return self.message


@runtime_checkable
class StreamingProvider(Protocol):
    def stream(
        self,
        *,
        messages: list[Message],
        tools: list[dict[str, Any]],
        model: str | None,
    ) -> Stream: ...
