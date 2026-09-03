from runa.core import Conversation, Message, Role, Run


def test_new_conversation_starts_empty():
    conversation = Conversation()
    assert conversation.messages == []
    assert conversation.state.get("anything") is None


def test_record_captures_a_terminal_runs_messages():
    conversation = Conversation()
    run = Run(input="hi")
    run.add_message(Message(role=Role.USER, content="hi"))
    run.add_message(Message(role=Role.ASSISTANT, content="hello"))

    conversation.record(run)

    assert [m.content for m in conversation.messages] == ["hi", "hello"]


def test_record_excludes_the_system_prompt():
    conversation = Conversation()
    run = Run(input="hi")
    run.add_message(Message(role=Role.SYSTEM, content="be helpful"))
    run.add_message(Message(role=Role.USER, content="hi"))

    conversation.record(run)

    assert [m.role for m in conversation.messages] == [Role.USER]


def test_record_replaces_rather_than_accumulates():
    conversation = Conversation()
    conversation.messages = [Message(role=Role.USER, content="stale")]
    run = Run(input="hi")
    run.add_message(Message(role=Role.USER, content="fresh"))

    conversation.record(run)

    assert [m.content for m in conversation.messages] == ["fresh"]
