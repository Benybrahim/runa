"""OpenAIProvider: a thin adapter between core.Message and OpenAI's API."""

import json
from typing import Any

import openai

from runa.core import Message, Role, ToolCall

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
    return Message(
        role=Role.ASSISTANT, content=choice.content or "", tool_calls=tool_calls
    )


class OpenAIProvider:
    """Provider backed by the OpenAI chat completions API.

    Satisfies the `Provider` protocol structurally: `complete(messages=...,
    tools=..., model=...) -> Message`. Wire-format translation lives in
    plain functions (`to_wire_messages`, `to_wire_tools`, `from_wire_message`)
    so it stays testable without a real API call.
    """

    def __init__(self, client: openai.OpenAI | None = None) -> None:
        self.client = client or openai.OpenAI()

    def complete(
        self,
        *,
        messages: list[Message],
        tools: list[dict[str, Any]],
        model: str | None,
    ) -> Message:
        response = self.client.chat.completions.create(
            model=model or DEFAULT_MODEL,
            messages=to_wire_messages(messages),
            tools=to_wire_tools(tools) if tools else openai.NOT_GIVEN,
        )
        return from_wire_message(response)


class AsyncOpenAIProvider:
    """The async counterpart to `OpenAIProvider`.

    Satisfies `AsyncProvider` structurally, backed by `openai.AsyncOpenAI`
    instead of `openai.OpenAI`. Shares the exact same wire-format functions
    as the sync provider — only the client and the `await` differ.
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
            messages=to_wire_messages(messages),
            tools=to_wire_tools(tools) if tools else openai.NOT_GIVEN,
        )
        return from_wire_message(response)
