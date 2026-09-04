"""AnthropicProvider: a thin adapter between core.Message and Anthropic's API."""

from collections.abc import AsyncIterator, Iterator
from typing import Any

import anthropic

from runa.core import Message, Role, ToolCall
from runa.runtime.async_provider import AsyncStream
from runa.runtime.provider import Stream, StreamChunk

DEFAULT_MODEL = "claude-sonnet-5"
DEFAULT_MAX_TOKENS = 4096


def to_wire_messages(messages: list[Message]) -> tuple[str, list[dict[str, Any]]]:
    """Split core Messages into Anthropic's (system, messages) shape."""
    system_parts: list[str] = []
    wire: list[dict[str, Any]] = []

    for message in messages:
        if message.role is Role.SYSTEM:
            system_parts.append(message.content)
        elif message.role is Role.TOOL:
            wire.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": message.tool_call_id,
                            "content": message.content,
                        }
                    ],
                }
            )
        elif message.role is Role.ASSISTANT and message.tool_calls:
            content: list[dict[str, Any]] = []
            if message.content:
                content.append({"type": "text", "text": message.content})
            for call in message.tool_calls:
                content.append(
                    {
                        "type": "tool_use",
                        "id": call.id,
                        "name": call.name,
                        "input": call.arguments,
                    }
                )
            wire.append({"role": "assistant", "content": content})
        else:
            wire.append({"role": message.role.value, "content": message.content})

    return "\n\n".join(system_parts), wire


def to_wire_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "name": tool["name"],
            "description": tool["description"],
            "input_schema": tool["parameters"],
        }
        for tool in tools
    ]


def from_wire_message(response: Any) -> Message:
    """Convert an Anthropic API response into a core Message."""
    text = ""
    tool_calls: list[ToolCall] = []

    for block in response.content:
        if block.type == "text":
            text += block.text
        elif block.type == "tool_use":
            tool_calls.append(
                ToolCall(name=block.name, arguments=dict(block.input), id=block.id)
            )

    usage = getattr(response, "usage", None)
    return Message(
        role=Role.ASSISTANT,
        content=text,
        tool_calls=tool_calls,
        usage=from_wire_usage(usage) if usage is not None else None,
    )


def from_wire_usage(usage: Any) -> dict[str, int]:
    """Normalize Anthropic's `Usage` into Runa's common usage shape."""
    return {
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
    }


class AnthropicProvider:
    """Provider backed by the Anthropic Messages API.

    Satisfies the `Provider` protocol structurally: `complete(messages=...,
    tools=..., model=...) -> Message`. Wire-format translation is exposed as
    plain functions (`to_wire_messages`, `to_wire_tools`, `from_wire_message`)
    so it stays testable without a real API call.
    """

    def __init__(
        self,
        client: anthropic.Anthropic | None = None,
        *,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> None:
        self.client = client or anthropic.Anthropic()
        self.max_tokens = max_tokens

    def complete(
        self,
        *,
        messages: list[Message],
        tools: list[dict[str, Any]],
        model: str | None,
    ) -> Message:
        system, wire_messages = to_wire_messages(messages)
        response = self.client.messages.create(
            model=model or DEFAULT_MODEL,
            max_tokens=self.max_tokens,
            system=system,
            messages=wire_messages,
            tools=to_wire_tools(tools) if tools else anthropic.NOT_GIVEN,
        )
        return from_wire_message(response)

    def stream(
        self,
        *,
        messages: list[Message],
        tools: list[dict[str, Any]],
        model: str | None,
    ) -> Stream:
        """Satisfies `StreamingProvider` structurally. Lazy: the request
        only fires once the returned `Stream` is iterated."""
        system, wire_messages = to_wire_messages(messages)

        def generate() -> Iterator[StreamChunk]:
            with self.client.messages.stream(
                model=model or DEFAULT_MODEL,
                max_tokens=self.max_tokens,
                system=system,
                messages=wire_messages,
                tools=to_wire_tools(tools) if tools else anthropic.NOT_GIVEN,
            ) as vendor_stream:
                for text in vendor_stream.text_stream:
                    yield StreamChunk(delta=text)
                result.message = from_wire_message(vendor_stream.get_final_message())

        result = Stream(generate())
        return result


class AsyncAnthropicProvider:
    """The async counterpart to `AnthropicProvider`.

    Satisfies `AsyncProvider` structurally, backed by `anthropic.AsyncAnthropic`
    instead of `anthropic.Anthropic`. Shares the exact same wire-format
    functions as the sync provider — only the client and the `await` differ.
    """

    def __init__(
        self,
        client: anthropic.AsyncAnthropic | None = None,
        *,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> None:
        self.client = client or anthropic.AsyncAnthropic()
        self.max_tokens = max_tokens

    async def complete(
        self,
        *,
        messages: list[Message],
        tools: list[dict[str, Any]],
        model: str | None,
    ) -> Message:
        system, wire_messages = to_wire_messages(messages)
        response = await self.client.messages.create(
            model=model or DEFAULT_MODEL,
            max_tokens=self.max_tokens,
            system=system,
            messages=wire_messages,
            tools=to_wire_tools(tools) if tools else anthropic.NOT_GIVEN,
        )
        return from_wire_message(response)

    def stream(
        self,
        *,
        messages: list[Message],
        tools: list[dict[str, Any]],
        model: str | None,
    ) -> AsyncStream:
        """Satisfies `AsyncStreamingProvider` structurally. Not `async def`
        itself — the request only fires once the returned `AsyncStream` is
        async-iterated."""
        system, wire_messages = to_wire_messages(messages)

        async def generate() -> AsyncIterator[StreamChunk]:
            async with self.client.messages.stream(
                model=model or DEFAULT_MODEL,
                max_tokens=self.max_tokens,
                system=system,
                messages=wire_messages,
                tools=to_wire_tools(tools) if tools else anthropic.NOT_GIVEN,
            ) as vendor_stream:
                async for text in vendor_stream.text_stream:
                    yield StreamChunk(delta=text)
                result.message = from_wire_message(
                    await vendor_stream.get_final_message()
                )

        result = AsyncStream(generate())
        return result
