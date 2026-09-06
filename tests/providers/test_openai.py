import asyncio
from types import SimpleNamespace
from typing import cast

import openai

from runa.core import Message, Role, ToolCall
from runa.providers.openai import (
    AsyncOpenAIProvider,
    OpenAIProvider,
    from_wire_message,
    to_wire_messages,
    to_wire_tools,
)


def test_system_and_user_messages_pass_through():
    messages = [
        Message(role=Role.SYSTEM, content="Be helpful."),
        Message(role=Role.USER, content="hi"),
    ]

    wire = to_wire_messages(messages)

    assert wire == [
        {"role": "system", "content": "Be helpful."},
        {"role": "user", "content": "hi"},
    ]


def test_assistant_tool_call_becomes_tool_calls_field():
    call = ToolCall(name="get_weather", arguments={"city": "Tokyo"}, id="call_1")
    messages = [Message(role=Role.ASSISTANT, tool_calls=[call])]

    wire = to_wire_messages(messages)

    assert wire == [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "get_weather",
                        "arguments": '{"city": "Tokyo"}',
                    },
                }
            ],
        }
    ]


def test_tool_result_message_becomes_tool_role_message():
    messages = [Message(role=Role.TOOL, content="sunny", tool_call_id="call_1")]

    wire = to_wire_messages(messages)

    assert wire == [{"role": "tool", "tool_call_id": "call_1", "content": "sunny"}]


def test_to_wire_tools_wraps_as_function_type():
    tools = [
        {"name": "get_weather", "description": "...", "parameters": {"type": "object"}}
    ]

    assert to_wire_tools(tools) == [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "...",
                "parameters": {"type": "object"},
            },
        }
    ]


def test_from_wire_message_collects_content_and_tool_calls():
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content="Let me check.",
                    tool_calls=[
                        SimpleNamespace(
                            id="call_1",
                            function=SimpleNamespace(
                                name="get_weather",
                                arguments='{"city": "Tokyo"}',
                            ),
                        )
                    ],
                )
            )
        ]
    )

    message = from_wire_message(response)

    assert message.role == Role.ASSISTANT
    assert message.content == "Let me check."
    assert message.tool_calls == [
        ToolCall(name="get_weather", arguments={"city": "Tokyo"}, id="call_1")
    ]


def test_from_wire_message_with_no_tool_calls():
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(message=SimpleNamespace(content="Hi.", tool_calls=None))
        ]
    )

    message = from_wire_message(response)

    assert message.content == "Hi."
    assert message.tool_calls == []


def test_from_wire_message_normalizes_usage_into_input_and_output_tokens():
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(message=SimpleNamespace(content="Hi.", tool_calls=None))
        ],
        usage=SimpleNamespace(prompt_tokens=12, completion_tokens=4),
    )

    message = from_wire_message(response)

    assert message.usage == {"input_tokens": 12, "output_tokens": 4}


def test_from_wire_message_with_no_usage_attribute_leaves_usage_none():
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(message=SimpleNamespace(content="Hi.", tool_calls=None))
        ]
    )

    message = from_wire_message(response)

    assert message.usage is None


def test_async_openai_provider_awaits_the_async_client():
    class FakeCompletions:
        async def create(self, **kwargs):
            self.kwargs = kwargs
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content="hi", tool_calls=None)
                    )
                ]
            )

    class FakeChat:
        def __init__(self):
            self.completions = FakeCompletions()

    class FakeAsyncClient:
        def __init__(self):
            self.chat = FakeChat()

    client = FakeAsyncClient()
    provider = AsyncOpenAIProvider(client=cast(openai.AsyncOpenAI, client))

    message = asyncio.run(
        provider.complete(
            messages=[Message(role=Role.USER, content="hello")],
            tools=[],
            model=None,
        )
    )

    assert message.content == "hi"
    assert client.chat.completions.kwargs["model"] == "gpt-5-nano"


def _completion_event(
    delta: str | None, type: str = "content.delta"
) -> SimpleNamespace:
    return SimpleNamespace(type=type, delta=delta)


class _FakeVendorStream:
    def __init__(self, events: list[SimpleNamespace], final: SimpleNamespace) -> None:
        self._events = events
        self._final = final

    def __iter__(self):
        return iter(self._events)

    def get_final_completion(self) -> SimpleNamespace:
        return self._final


class _FakeVendorStreamManager:
    def __init__(self, events: list[SimpleNamespace], final: SimpleNamespace) -> None:
        self._stream = _FakeVendorStream(events, final)

    def __enter__(self) -> _FakeVendorStream:
        return self._stream

    def __exit__(self, *exc: object) -> bool:
        return False


def test_openai_provider_stream_yields_content_deltas_only():
    events = [
        _completion_event("Let"),
        _completion_event(" me check."),
        _completion_event(None, type="content.done"),
    ]
    final = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="Let me check.", tool_calls=None)
            )
        ]
    )

    class FakeCompletions:
        def stream(self, **kwargs):
            self.kwargs = kwargs
            return _FakeVendorStreamManager(events, final)

    class FakeChat:
        def __init__(self):
            self.completions = FakeCompletions()

    class FakeClient:
        def __init__(self):
            self.chat = FakeChat()

    client = FakeClient()
    provider = OpenAIProvider(client=cast(openai.OpenAI, client))

    stream = provider.stream(
        messages=[Message(role=Role.USER, content="hi")], tools=[], model=None
    )
    chunks = [chunk.text for chunk in stream]

    assert chunks == ["Let", " me check."]
    assert stream.message is not None
    assert stream.message.content == "Let me check."
    assert client.chat.completions.kwargs["model"] == "gpt-5-nano"


class _FakeAsyncVendorStream:
    def __init__(self, events: list[SimpleNamespace], final: SimpleNamespace) -> None:
        self._events = events
        self._final = final

    async def __aiter__(self):
        for event in self._events:
            yield event

    async def get_final_completion(self) -> SimpleNamespace:
        return self._final


class _FakeAsyncVendorStreamManager:
    def __init__(self, events: list[SimpleNamespace], final: SimpleNamespace) -> None:
        self._stream = _FakeAsyncVendorStream(events, final)

    async def __aenter__(self) -> _FakeAsyncVendorStream:
        return self._stream

    async def __aexit__(self, *exc: object) -> bool:
        return False


def test_async_openai_provider_stream_yields_content_deltas_only():
    events = [_completion_event("hi"), _completion_event(" there")]
    final = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="hi there", tool_calls=None)
            )
        ]
    )

    class FakeCompletions:
        def stream(self, **kwargs):
            self.kwargs = kwargs
            return _FakeAsyncVendorStreamManager(events, final)

    class FakeChat:
        def __init__(self):
            self.completions = FakeCompletions()

    class FakeAsyncClient:
        def __init__(self):
            self.chat = FakeChat()

    client = FakeAsyncClient()
    provider = AsyncOpenAIProvider(client=cast(openai.AsyncOpenAI, client))
    stream = provider.stream(
        messages=[Message(role=Role.USER, content="hi")], tools=[], model=None
    )

    async def collect() -> list[str]:
        return [chunk.text async for chunk in stream]

    chunks = asyncio.run(collect())

    assert chunks == ["hi", " there"]
    assert stream.message is not None
    assert stream.message.content == "hi there"
    assert client.chat.completions.kwargs["model"] == "gpt-5-nano"
