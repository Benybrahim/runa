"""Provider: the contract between the runtime and a specific model API.

Concrete adapters live in `providers/` and translate between this contract
and a vendor's wire format. The runtime depends only on this protocol, never
on a specific vendor.

Async is the source of truth: `complete()` is a coroutine, and `Executor`
(runtime/executor.py) awaits it directly, so independent tool calls a model
turn asks for can run concurrently via `asyncio.gather`. There is no
separate synchronous Provider to maintain in parallel; a script that wants
to call a Provider directly outside an Agent does the same thing
`Agent.run_sync()` does for a whole run, `asyncio.run(provider.complete(...))`.

`StreamingProvider` is a separate, optional protocol, not a second method
tacked onto `Provider`: a Provider that only implements `complete()` still
satisfies `Provider` on its own (every `FakeProvider` in tests included);
one that also implements `stream()` additionally satisfies
`StreamingProvider`, structurally, with no base class to opt into.
"""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from runa.core import Message


class Provider(Protocol):
    async def complete(
        self,
        *,
        messages: list[Message],
        tools: list[dict[str, Any]],
        model: str | None,
    ) -> Message: ...


@dataclass
class RetryingProvider:
    """Wraps a Provider, retrying `complete()` on failure before giving up.

    Without this, any transient failure from the model API itself (a rate
    limit, a timeout, a dropped connection) fails the call on the first
    hit: `RetryStrategy` (`runtime/retry.py`) only retries *tool* calls
    under `Executor`, since a tool call can have a real side effect a blind
    retry might repeat. A model call has no such hazard: nothing is written
    anywhere until `complete()` returns, so a failed attempt leaves nothing
    to undo; retrying just repeats the same read-only request.

    Retries every exception by default, up to `max_retries` times, with
    delays that double each attempt starting at `backoff` seconds, the same
    blunt, type-agnostic policy `RetryStrategy` already uses for tool calls
    (no attempt to special-case "transient" vs "permanent" here either).
    Pass `is_retryable` to narrow that down for a specific Provider's own
    exception types (e.g. only `anthropic.RateLimitError` and
    `anthropic.APIConnectionError`); those types are vendor-specific and
    belong at the call site, not in this generic wrapper (architecture.md
    §5: "Provider-specific concepts must remain inside provider adapters").

    `sleep` defaults to `asyncio.sleep`, so a retry delay doesn't block the
    event loop.

    Satisfies `Provider` structurally, so it drops in anywhere a Provider is
    expected: `Judge(RetryingProvider(AnthropicProvider()))`. Wraps
    `complete()` only: a Provider that also implements `stream()` stops
    satisfying `StreamingProvider` once wrapped, since a partially delivered
    stream can't be safely retried from the start once some chunks have
    already reached `on_chunk`.
    """

    provider: Provider
    max_retries: int = 3
    backoff: float = 1.0
    is_retryable: Callable[[Exception], bool] = lambda exc: True
    sleep: Callable[[float], Awaitable[Any]] = field(default=asyncio.sleep, repr=False)

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


@dataclass
class StreamChunk:
    """One incremental piece of a streamed model response: a text delta."""

    text: str


class Stream:
    """What `StreamingProvider.stream()` returns.

    `async for chunk in stream` for `StreamChunk`s as they arrive. `message`
    holds the same `Message` `complete()` would have returned for the same
    call. A concrete Provider's `stream()` sets it once its underlying
    vendor stream is exhausted, so read it only after the iterator is
    exhausted (`drain()` does both in one call).
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
            "Stream exhausted without setting `message`: the "
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
    ) -> Stream:
        """Not `async def`: returns a `Stream` immediately; the request
        itself only fires once that Stream is async-iterated."""
        ...
