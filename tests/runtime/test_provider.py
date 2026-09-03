import asyncio

import pytest

from runa.core import Message, Role
from runa.runtime.async_provider import AsyncStream
from runa.runtime.provider import Stream, StreamChunk


def test_stream_yields_chunks_in_order():
    final = Message(role=Role.ASSISTANT, content="hi there")

    def generate():
        yield StreamChunk(delta="hi")
        yield StreamChunk(delta=" there")
        stream.message = final

    stream = Stream(generate())

    assert [c.delta for c in stream] == ["hi", " there"]
    assert stream.message is final


def test_stream_drain_consumes_remaining_chunks_and_returns_the_message():
    final = Message(role=Role.ASSISTANT, content="hi")

    def generate():
        yield StreamChunk(delta="hi")
        stream.message = final

    stream = Stream(generate())

    assert stream.drain() is final


def test_stream_drain_asserts_if_message_was_never_set():
    def generate():
        yield StreamChunk(delta="hi")
        # forgets to set stream.message

    stream = Stream(generate())

    with pytest.raises(AssertionError):
        stream.drain()


def test_async_stream_yields_chunks_and_drain_returns_the_message():
    final = Message(role=Role.ASSISTANT, content="hi there")

    async def generate():
        yield StreamChunk(delta="hi")
        yield StreamChunk(delta=" there")
        stream.message = final

    stream = AsyncStream(generate())

    async def collect():
        return [c.delta async for c in stream]

    assert asyncio.run(collect()) == ["hi", " there"]
    assert stream.message is final


def test_async_stream_drain_consumes_remaining_chunks():
    final = Message(role=Role.ASSISTANT, content="hi")

    async def generate():
        yield StreamChunk(delta="hi")
        stream.message = final

    stream = AsyncStream(generate())

    assert asyncio.run(stream.drain()) is final
