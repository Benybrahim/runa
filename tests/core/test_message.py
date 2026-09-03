from runa.core import Message, Role, ToolCall


def test_tool_call_completed_reflects_a_successful_attempt():
    call = ToolCall(name="web_search", arguments={"query": "fusion"})
    assert not call.completed
    call.attempts += 1
    call.result = ["result1"]
    assert call.completed


def test_tool_call_completed_is_true_even_when_the_result_is_none():
    # A Tool can legitimately return None — that's not "never ran".
    call = ToolCall(name="send_email", arguments={"to": "a@b.com"})
    call.attempts += 1
    call.result = None
    assert call.completed


def test_tool_call_completed_is_false_after_a_failed_attempt():
    call = ToolCall(name="web_search", arguments={"query": "fusion"})
    call.attempts += 1
    call.error = "boom"
    assert not call.completed


def test_tool_call_error_and_attempts_default_to_unset():
    call = ToolCall(name="web_search", arguments={"query": "fusion"})
    assert call.error is None
    assert call.attempts == 0


def test_message_defaults():
    message = Message(role=Role.USER, content="hi")
    assert message.tool_calls == []
    assert message.tool_call_id is None
