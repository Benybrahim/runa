from runa.core import Conversation, Message, Role, Run
from runa.runtime._shared import model_context


def test_model_context_with_no_conversation_is_just_the_runs_own_messages():
    run = Run(input="hi")
    run.add_message(Message(role=Role.SYSTEM, content="be terse"))
    run.add_message(Message(role=Role.USER, content="hi"))

    assert model_context(run, None) == run.messages


def test_model_context_inserts_history_after_the_leading_system_message():
    conversation = Conversation()
    conversation.messages = [
        Message(role=Role.USER, content="earlier question"),
        Message(role=Role.ASSISTANT, content="earlier answer"),
    ]
    run = Run(input="hi")
    run.add_message(Message(role=Role.SYSTEM, content="be terse"))
    run.add_message(Message(role=Role.USER, content="new question"))

    contents = [m.content for m in model_context(run, conversation)]

    assert contents == [
        "be terse",
        "earlier question",
        "earlier answer",
        "new question",
    ]


def test_model_context_prepends_history_when_there_is_no_system_message():
    conversation = Conversation()
    conversation.messages = [Message(role=Role.USER, content="earlier question")]
    run = Run(input="hi")
    run.add_message(Message(role=Role.USER, content="new question"))

    contents = [m.content for m in model_context(run, conversation)]

    assert contents == ["earlier question", "new question"]


def test_model_context_does_not_hoist_a_later_transfer_system_message():
    """Only `run.messages[0]` counts as the leading system prompt history is
    inserted after; a SYSTEM message added later (e.g. by a Transfer
    delegation) stays in its natural chronological position."""
    conversation = Conversation()
    conversation.messages = [Message(role=Role.USER, content="earlier question")]
    run = Run(input="hi")
    run.add_message(Message(role=Role.SYSTEM, content="triage instructions"))
    run.add_message(Message(role=Role.USER, content="new question"))
    run.add_message(Message(role=Role.TOOL, content="transferred", tool_call_id="tc-1"))
    run.add_message(Message(role=Role.SYSTEM, content="billing instructions"))

    contents = [m.content for m in model_context(run, conversation)]

    assert contents == [
        "triage instructions",
        "earlier question",
        "new question",
        "transferred",
        "billing instructions",
    ]
