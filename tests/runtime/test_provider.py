import asyncio

import pytest

from runa.core import Message, Role
from runa.runtime.async_provider import AsyncRetryingProvider, AsyncStream
from runa.runtime.provider import RetryingProvider, Stream, StreamChunk


class FlakyProvider:
    """Fails `fail_times` times, then succeeds. Records every attempt."""

    def __init__(self, fail_times: int, result: Message | None = None) -> None:
        self.fail_times = fail_times
        self.result = result or Message(role=Role.ASSISTANT, content="ok")
        self.attempts = 0

    def complete(self, *, messages, tools, model):
        self.attempts += 1
        if self.attempts <= self.fail_times:
            raise ConnectionError("transient failure")
        return self.result


class AsyncFlakyProvider:
    def __init__(self, fail_times: int, result: Message | None = None) -> None:
        self.fail_times = fail_times
        self.result = result or Message(role=Role.ASSISTANT, content="ok")
        self.attempts = 0

    async def complete(self, *, messages, tools, model):
        self.attempts += 1
        if self.attempts <= self.fail_times:
            raise ConnectionError("transient failure")
        return self.result


def test_retrying_provider_succeeds_after_transient_failures():
    inner = FlakyProvider(fail_times=2)
    sleeps: list[float] = []
    provider = RetryingProvider(inner, max_retries=3, backoff=1.0, sleep=sleeps.append)

    result = provider.complete(messages=[], tools=[], model=None)

    assert result is inner.result
    assert inner.attempts == 3
    assert sleeps == [1.0, 2.0]  # exponential backoff between attempts 1->2, 2->3


def test_retrying_provider_raises_once_retries_are_exhausted():
    inner = FlakyProvider(fail_times=10)
    provider = RetryingProvider(inner, max_retries=2, sleep=lambda s: None)

    with pytest.raises(ConnectionError):
        provider.complete(messages=[], tools=[], model=None)

    assert inner.attempts == 3  # the first attempt plus 2 retries


def test_retrying_provider_does_not_retry_when_is_retryable_says_no():
    inner = FlakyProvider(fail_times=10)
    provider = RetryingProvider(
        inner, max_retries=5, is_retryable=lambda exc: False, sleep=lambda s: None
    )

    with pytest.raises(ConnectionError):
        provider.complete(messages=[], tools=[], model=None)

    assert inner.attempts == 1  # failed on the very first attempt, no retry


def test_retrying_provider_does_not_retry_a_successful_call():
    inner = FlakyProvider(fail_times=0)
    provider = RetryingProvider(inner, sleep=lambda s: None)

    provider.complete(messages=[], tools=[], model=None)

    assert inner.attempts == 1


def test_async_retrying_provider_succeeds_after_transient_failures():
    inner = AsyncFlakyProvider(fail_times=2)
    sleeps: list[float] = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    provider = AsyncRetryingProvider(
        inner, max_retries=3, backoff=1.0, sleep=fake_sleep
    )

    result = asyncio.run(provider.complete(messages=[], tools=[], model=None))

    assert result is inner.result
    assert inner.attempts == 3
    assert sleeps == [1.0, 2.0]


def test_async_retrying_provider_raises_once_retries_are_exhausted():
    async def fake_sleep(seconds):
        pass

    inner = AsyncFlakyProvider(fail_times=10)
    provider = AsyncRetryingProvider(inner, max_retries=2, sleep=fake_sleep)

    with pytest.raises(ConnectionError):
        asyncio.run(provider.complete(messages=[], tools=[], model=None))

    assert inner.attempts == 3


def test_stream_yields_chunks_in_order():
    final = Message(role=Role.ASSISTANT, content="hi there")

    def generate():
        yield StreamChunk(text="hi")
        yield StreamChunk(text=" there")
        stream.message = final

    stream = Stream(generate())

    assert [c.text for c in stream] == ["hi", " there"]
    assert stream.message is final


def test_stream_drain_consumes_remaining_chunks_and_returns_the_message():
    final = Message(role=Role.ASSISTANT, content="hi")

    def generate():
        yield StreamChunk(text="hi")
        stream.message = final

    stream = Stream(generate())

    assert stream.drain() is final


def test_stream_drain_asserts_if_message_was_never_set():
    def generate():
        yield StreamChunk(text="hi")
        # forgets to set stream.message

    stream = Stream(generate())

    with pytest.raises(AssertionError):
        stream.drain()


def test_async_stream_yields_chunks_and_drain_returns_the_message():
    final = Message(role=Role.ASSISTANT, content="hi there")

    async def generate():
        yield StreamChunk(text="hi")
        yield StreamChunk(text=" there")
        stream.message = final

    stream = AsyncStream(generate())

    async def collect():
        return [c.text async for c in stream]

    assert asyncio.run(collect()) == ["hi", " there"]
    assert stream.message is final


def test_async_stream_drain_consumes_remaining_chunks():
    final = Message(role=Role.ASSISTANT, content="hi")

    async def generate():
        yield StreamChunk(text="hi")
        stream.message = final

    stream = AsyncStream(generate())

    assert asyncio.run(stream.drain()) is final
