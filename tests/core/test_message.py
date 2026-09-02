from runa.core import Message, Role, ToolCall


def test_tool_call_completed_reflects_result():
    call = ToolCall(name="web_search", arguments={"query": "fusion"})
    assert not call.completed
    call.result = ["result1"]
    assert call.completed


def test_tool_call_error_and_attempts_default_to_unset():
    call = ToolCall(name="web_search", arguments={"query": "fusion"})
    assert call.error is None
    assert call.attempts == 0


def test_message_defaults():
    message = Message(role=Role.USER, content="hi")
    assert message.tool_calls == []
    assert message.tool_call_id is None
