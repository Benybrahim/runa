from runa.core import Message, Role, Run, ToolCall
from runa.runtime.retry import RetryStrategy
from runa.runtime.strategy import CallModel, CallTool, Complete, Fail


def test_empty_run_calls_model():
    run = Run(input="hi")
    assert isinstance(RetryStrategy().step(run), CallModel)


def test_errored_idempotent_tool_call_retries_while_attempts_remain():
    run = Run(input="hi")
    call = ToolCall(name="flaky", error="timeout", attempts=1, idempotent=True)
    run.add_message(Message(role=Role.ASSISTANT, tool_calls=[call]))

    action = RetryStrategy(max_retries=3).step(run)

    assert isinstance(action, CallTool)
    assert action.tool_call is call


def test_errored_idempotent_tool_call_fails_once_retries_are_exhausted():
    run = Run(input="hi")
    call = ToolCall(name="flaky", error="timeout", attempts=4, idempotent=True)
    run.add_message(Message(role=Role.ASSISTANT, tool_calls=[call]))

    action = RetryStrategy(max_retries=3).step(run)

    assert isinstance(action, Fail)
    assert action.error == "timeout"


def test_errored_non_idempotent_tool_call_fails_immediately():
    # Not idempotent: the exception left its effect unknown, so repeating
    # it risks duplicating a real side effect — no retry even though
    # attempts are well within max_retries.
    run = Run(input="hi")
    call = ToolCall(name="charge_card", error="timeout", attempts=1)
    run.add_message(Message(role=Role.ASSISTANT, tool_calls=[call]))

    action = RetryStrategy(max_retries=3).step(run)

    assert isinstance(action, Fail)
    assert action.error == "timeout"


def test_successful_tool_call_is_not_retried():
    run = Run(input="hi")
    call = ToolCall(name="flaky", result="ok", attempts=2)
    run.add_message(Message(role=Role.ASSISTANT, content="", tool_calls=[call]))

    assert isinstance(RetryStrategy().step(run), Complete)
