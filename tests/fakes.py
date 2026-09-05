"""Fakes for testing provider-dependent code without real API calls."""

from typing import Any

from runa.core import Message
from runa.runtime.async_provider import AsyncStream
from runa.runtime.provider import Stream, StreamChunk


class FakeProvider:
    """A scripted Provider: returns queued Messages in order, one per call."""

    def __init__(self, responses: list[Message]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def complete(
        self,
        *,
        messages: list[Message],
        tools: list[dict[str, Any]],
        model: str | None,
    ) -> Message:
        self.calls.append({"messages": list(messages), "tools": tools, "model": model})
        if not self._responses:
            raise AssertionError("FakeProvider ran out of scripted responses")
        return self._responses.pop(0)


class FakeStreamingProvider:
    """A scripted `StreamingProvider`: same contract as `FakeProvider`, plus
    `stream()`. Splits each response's `.content` into one-character
    `StreamChunk`s before delivering the same `Message` `complete()` would;
    a response with only `tool_calls` and no `.content` streams zero
    chunks, matching how a real tool-call turn carries little or no text.
    """

    def __init__(self, responses: list[Message]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def _next_response(
        self, *, messages: list[Message], tools: Any, model: Any
    ) -> Message:
        self.calls.append({"messages": list(messages), "tools": tools, "model": model})
        if not self._responses:
            raise AssertionError("FakeStreamingProvider ran out of scripted responses")
        return self._responses.pop(0)

    def complete(
        self,
        *,
        messages: list[Message],
        tools: list[dict[str, Any]],
        model: str | None,
    ) -> Message:
        return self._next_response(messages=messages, tools=tools, model=model)

    def stream(
        self,
        *,
        messages: list[Message],
        tools: list[dict[str, Any]],
        model: str | None,
    ) -> Stream:
        response = self._next_response(messages=messages, tools=tools, model=model)

        def generate():
            for character in response.content:
                yield StreamChunk(delta=character)
            stream.message = response

        stream = Stream(generate())
        return stream


class FakeAsyncStreamingProvider:
    """The async counterpart to `FakeStreamingProvider`."""

    def __init__(self, responses: list[Message]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def _next_response(
        self, *, messages: list[Message], tools: Any, model: Any
    ) -> Message:
        self.calls.append({"messages": list(messages), "tools": tools, "model": model})
        if not self._responses:
            raise AssertionError(
                "FakeAsyncStreamingProvider ran out of scripted responses"
            )
        return self._responses.pop(0)

    async def complete(
        self,
        *,
        messages: list[Message],
        tools: list[dict[str, Any]],
        model: str | None,
    ) -> Message:
        return self._next_response(messages=messages, tools=tools, model=model)

    def stream(
        self,
        *,
        messages: list[Message],
        tools: list[dict[str, Any]],
        model: str | None,
    ) -> AsyncStream:
        response = self._next_response(messages=messages, tools=tools, model=model)

        async def generate():
            for character in response.content:
                yield StreamChunk(delta=character)
            stream.message = response

        stream = AsyncStream(generate())
        return stream


class FakeAsyncProvider:
    """A scripted AsyncProvider: same contract as FakeProvider, but async."""

    def __init__(self, responses: list[Message]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    async def complete(
        self,
        *,
        messages: list[Message],
        tools: list[dict[str, Any]],
        model: str | None,
    ) -> Message:
        self.calls.append({"messages": list(messages), "tools": tools, "model": model})
        if not self._responses:
            raise AssertionError("FakeAsyncProvider ran out of scripted responses")
        return self._responses.pop(0)
