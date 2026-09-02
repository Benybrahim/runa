from types import SimpleNamespace

from runa.core import Message, Role, ToolCall
from runa.providers.openai import from_wire_message, to_wire_messages, to_wire_tools


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
        choices=[SimpleNamespace(message=SimpleNamespace(content="Hi.", tool_calls=None))]
    )

    message = from_wire_message(response)

    assert message.content == "Hi."
    assert message.tool_calls == []
