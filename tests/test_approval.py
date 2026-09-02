import pytest

from runa.approval import UnknownToolCall, approve, deny
from runa.core import Message, Role, Run, RunStatus, ToolCall


def _run_awaiting_approval() -> tuple[Run, ToolCall]:
    call = ToolCall(name="SendEmail", arguments={"to": "a@example.com"})
    run = Run(input="email someone")
    run.start()
    run.add_message(Message(role=Role.ASSISTANT, tool_calls=[call]))
    run.require_approval(call.id)
    return run, call


def test_approve_marks_the_tool_call_approved_and_resumes_the_run():
    run, call = _run_awaiting_approval()

    approve(run, call.id)

    assert call.approved is True
    assert run.status == RunStatus.RUNNING


def test_deny_marks_the_tool_call_denied_and_fails_the_run():
    run, call = _run_awaiting_approval()

    deny(run, call.id, reason="not authorized")

    assert call.approved is False
    assert run.status == RunStatus.FAILED
    assert "not authorized" in run.events[-1].data["error"]


def test_deny_without_reason_still_fails_the_run():
    run, call = _run_awaiting_approval()

    deny(run, call.id)

    assert run.status == RunStatus.FAILED


def test_approve_unknown_tool_call_raises():
    run, _ = _run_awaiting_approval()

    with pytest.raises(UnknownToolCall):
        approve(run, "does-not-exist")


def test_deny_unknown_tool_call_raises():
    run, _ = _run_awaiting_approval()

    with pytest.raises(UnknownToolCall):
        deny(run, "does-not-exist")
