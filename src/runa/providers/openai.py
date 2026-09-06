"""OpenAIProvider: a thin adapter between core.Message and OpenAI's API."""

import json
from collections.abc import AsyncIterator
from typing import Any, cast

import openai
from openai.types.chat import ChatCompletionMessageParam, ChatCompletionToolUnionParam

from runa.core import Message, Role, ToolCall
from runa.runtime.provider import Stream, StreamChunk

DEFAULT_MODEL = "gpt-5-nano"


def to_wire_messages(messages: list[Message]) -> list[dict[str, Any]]:
    """Convert core Messages into OpenAI's chat-completions message list."""
    wire: list[dict[str, Any]] = []

    for message in messages:
        if message.role is Role.TOOL:
            wire.append(
                {
                    "role": "tool",
                    "tool_call_id": message.tool_call_id,
                    "content": message.content,
                }
            )
        elif message.role is Role.ASSISTANT and message.tool_calls:
            wire.append(
                {
                    "role": "assistant",
                    "content": message.content or None,
                    "tool_calls": [
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {
                                "name": call.name,
                                "arguments": json.dumps(call.arguments),
                            },
                        }
                        for call in message.tool_calls
                    ],
                }
            )
        else:
            wire.append({"role": message.role.value, "content": message.content})

    return wire


def to_wire_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["parameters"],
            },
        }
        for tool in tools
    ]


def from_wire_message(response: Any) -> Message:
    """Convert an OpenAI chat-completion response into a core Message."""
    choice = response.choices[0].message
    tool_calls = [
        ToolCall(
            name=call.function.name,
            arguments=json.loads(call.function.arguments),
            id=call.id,
        )
        for call in (choice.tool_calls or [])
    ]
    usage = getattr(response, "usage", None)
    return Message(
        role=Role.ASSISTANT,
        content=choice.content or "",
        tool_calls=tool_calls,
        usage=from_wire_usage(usage) if usage is not None else None,
    )


def from_wire_usage(usage: Any) -> dict[str, int]:
    """Normalize OpenAI's `CompletionUsage` into Runa's common usage shape."""
    return {
        "input_tokens": usage.prompt_tokens,
        "output_tokens": usage.completion_tokens,
    }


class OpenAIProvider:
    """Provider backed by the OpenAI chat completions API.

    Satisfies the `Provider` protocol structurally: `async complete(
    messages=..., tools=..., model=...) -> Message`. Wire-format
    translation lives in plain functions (`to_wire_messages`,
    `to_wire_tools`, `from_wire_message`) so it stays testable without a
    real API call.

    Backed by `openai.AsyncOpenAI`: async is Runa's canonical execution
    path, so there is no separate synchronous counterpart to maintain here.
    Code that needs a blocking call can await this from
    `asyncio.run(...)`, the same thing `Agent.run_sync()` does for a whole
    Executor run.
    """

    def __init__(self, client: openai.AsyncOpenAI | None = None) -> None:
        self.client = client or openai.AsyncOpenAI()

    async def complete(
        self,
        *,
        messages: list[Message],
        tools: list[dict[str, Any]],
        model: str | None,
    ) -> Message:
        response = await self.client.chat.completions.create(
            model=model or DEFAULT_MODEL,
            messages=cast(list[ChatCompletionMessageParam], to_wire_messages(messages)),
            tools=cast(list[ChatCompletionToolUnionParam], to_wire_tools(tools))
            if tools
            else openai.omit,
        )
        return from_wire_message(response)

    def stream(
        self,
        *,
        messages: list[Message],
        tools: list[dict[str, Any]],
        model: str | None,
    ) -> Stream:
        """Satisfies `StreamingProvider` structurally. Not `async def`
        itself: the request only fires once the returned `Stream` is
        async-iterated."""

        async def generate() -> AsyncIterator[StreamChunk]:
            async with self.client.chat.completions.stream(
                model=model or DEFAULT_MODEL,
                messages=cast(
                    list[ChatCompletionMessageParam], to_wire_messages(messages)
                ),
                tools=cast(list[ChatCompletionToolUnionParam], to_wire_tools(tools))
                if tools
                else openai.omit,
            ) as vendor_stream:
                async for event in vendor_stream:
                    if event.type == "content.delta" and event.delta:
                        yield StreamChunk(text=event.delta)
                result.message = from_wire_message(
                    await vendor_stream.get_final_completion()
                )

        result = Stream(generate())
        return result
