from runa.core import Message, Role, ToolCall


def test_tool_call_succeeded_reflects_a_successful_attempt():
    call = ToolCall(name="web_search", arguments={"query": "fusion"})
    assert not call.succeeded
    call.attempts += 1
    call.result = ["result1"]
    assert call.succeeded


def test_tool_call_succeeded_is_true_even_when_the_result_is_none():
    # A Tool can legitimately return None: that's not "never ran".
    call = ToolCall(name="send_email", arguments={"to": "a@b.com"})
    call.attempts += 1
    call.result = None
    assert call.succeeded


def test_tool_call_succeeded_is_false_after_a_failed_attempt():
    call = ToolCall(name="web_search", arguments={"query": "fusion"})
    call.attempts += 1
    call.error = "boom"
    assert not call.succeeded


def test_tool_call_not_succeeded_does_not_distinguish_pending_from_failed():
    # `not succeeded` is true both before any attempt and after a failed
    # one; callers that need to tell those apart read attempts/error
    # directly (see strategy.py, retry.py), not a separate lifecycle flag.
    never_attempted = ToolCall(name="web_search", arguments={"query": "fusion"})
    failed = ToolCall(name="web_search", arguments={"query": "fusion"})
    failed.attempts += 1
    failed.error = "boom"

    assert not never_attempted.succeeded
    assert not failed.succeeded
    assert never_attempted.attempts == 0
    assert failed.attempts == 1


def test_tool_call_approved_is_tristate_and_independent_of_succeeded():
    call = ToolCall(name="send_refund", arguments={"order_id": "A1"})
    assert call.approved is None
    assert not call.succeeded

    call.approved = False
    assert not call.succeeded  # denial doesn't imply an attempt happened

    call.approved = True
    call.attempts += 1
    call.result = "refunded"
    assert call.succeeded


def test_tool_call_error_and_attempts_default_to_unset():
    call = ToolCall(name="web_search", arguments={"query": "fusion"})
    assert call.error is None
    assert call.attempts == 0


def test_message_defaults():
    message = Message(role=Role.USER, content="hi")
    assert message.tool_calls == []
    assert message.tool_call_id is None
