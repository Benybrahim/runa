import asyncio
from types import SimpleNamespace

from runa.core import Message, Role, ToolCall
from runa.providers.anthropic import (
    AsyncAnthropicProvider,
    from_wire_message,
    to_wire_messages,
    to_wire_tools,
)


def test_system_messages_are_pulled_out_and_joined():
    messages = [
        Message(role=Role.SYSTEM, content="Be helpful."),
        Message(role=Role.USER, content="hi"),
    ]

    system, wire = to_wire_messages(messages)

    assert system == "Be helpful."
    assert wire == [{"role": "user", "content": "hi"}]


def test_multiple_system_messages_are_joined_with_blank_line():
    messages = [
        Message(role=Role.SYSTEM, content="Be helpful."),
        Message(role=Role.SYSTEM, content="Be terse."),
    ]

    system, _ = to_wire_messages(messages)

    assert system == "Be helpful.\n\nBe terse."


def test_assistant_tool_call_becomes_tool_use_block():
    call = ToolCall(name="get_weather", arguments={"city": "Tokyo"}, id="call_1")
    messages = [Message(role=Role.ASSISTANT, tool_calls=[call])]

    _, wire = to_wire_messages(messages)

    assert wire == [
        {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "call_1",
                    "name": "get_weather",
                    "input": {"city": "Tokyo"},
                }
            ],
        }
    ]


def test_assistant_text_before_tool_call_is_kept_as_a_text_block():
    call = ToolCall(name="get_weather", arguments={"city": "Tokyo"}, id="call_1")
    messages = [
        Message(role=Role.ASSISTANT, content="Let me check.", tool_calls=[call])
    ]

    _, wire = to_wire_messages(messages)

    assert wire[0]["content"][0] == {"type": "text", "text": "Let me check."}


def test_tool_result_message_becomes_user_tool_result_block():
    messages = [Message(role=Role.TOOL, content="sunny", tool_call_id="call_1")]

    _, wire = to_wire_messages(messages)

    assert wire == [
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "call_1", "content": "sunny"}
            ],
        }
    ]


def test_to_wire_tools_renames_parameters_to_input_schema():
    tools = [
        {"name": "get_weather", "description": "...", "parameters": {"type": "object"}}
    ]

    assert to_wire_tools(tools) == [
        {
            "name": "get_weather",
            "description": "...",
            "input_schema": {"type": "object"},
        }
    ]


def test_from_wire_message_collects_text_and_tool_use_blocks():
    response = SimpleNamespace(
        content=[
            SimpleNamespace(type="text", text="Let me check. "),
            SimpleNamespace(
                type="tool_use",
                id="call_1",
                name="get_weather",
                input={"city": "Tokyo"},
            ),
        ]
    )

    message = from_wire_message(response)

    assert message.role == Role.ASSISTANT
    assert message.content == "Let me check. "
    assert message.tool_calls == [
        ToolCall(name="get_weather", arguments={"city": "Tokyo"}, id="call_1")
    ]


def test_from_wire_message_with_no_tool_use_blocks():
    response = SimpleNamespace(content=[SimpleNamespace(type="text", text="Hi.")])

    message = from_wire_message(response)

    assert message.content == "Hi."
    assert message.tool_calls == []


def test_async_anthropic_provider_awaits_the_async_client():
    class FakeMessages:
        async def create(self, **kwargs):
            self.kwargs = kwargs
            return SimpleNamespace(content=[SimpleNamespace(type="text", text="hi")])

    class FakeAsyncClient:
        def __init__(self):
            self.messages = FakeMessages()

    client = FakeAsyncClient()
    provider = AsyncAnthropicProvider(client=client)

    message = asyncio.run(
        provider.complete(
            messages=[Message(role=Role.USER, content="hello")],
            tools=[],
            model=None,
        )
    )

    assert message.content == "hi"
    assert client.messages.kwargs["model"] == "claude-sonnet-5"
