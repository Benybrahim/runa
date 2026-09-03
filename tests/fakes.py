"""Fakes for testing provider-dependent code without real API calls."""

from typing import Any

from runa.core import Message


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
