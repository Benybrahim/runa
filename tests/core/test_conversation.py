import threading

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


def test_concurrent_record_calls_never_tear_or_interleave_messages():
    """Many threads racing `record()` must each see a coherent, single
    Run's messages — never a mix of two Runs' messages spliced together.
    Which Run's `record()` finishes last is unspecified (see the
    last-write-wins test below); that it's *one whole Run's* messages,
    not a corrupted blend, is what the lock in `record()` guarantees."""
    conversation = Conversation()
    runs = []
    for i in range(20):
        run = Run(input=f"run {i}")
        run.add_message(Message(role=Role.USER, content=f"user-{i}"))
        run.add_message(Message(role=Role.ASSISTANT, content=f"assistant-{i}"))
        runs.append(run)

    threads = [
        threading.Thread(target=conversation.record, args=(run,)) for run in runs
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    contents = [m.content for m in conversation.messages]
    assert len(contents) == 2
    winner = contents[0].split("-")[1]
    assert contents == [f"user-{winner}", f"assistant-{winner}"]


def test_concurrent_runs_against_one_conversation_silently_lose_an_update():
    """Documents the semantics `Conversation`'s docstring states explicitly:
    two Runs that overlap in time against the same Conversation are not
    merged. Each seeds its history from the Conversation as it was when
    that Run started; whichever `record()` call happens last simply
    replaces `.messages`, silently dropping the other Run's turn."""
    conversation = Conversation()

    run_a = Run(input="a", conversation=conversation)
    run_b = Run(input="b", conversation=conversation)
    # Both Runs "start" against the same, still-empty history.
    seeded_a = list(conversation.messages)
    seeded_b = list(conversation.messages)
    run_a.messages = [*seeded_a, Message(role=Role.USER, content="from a")]
    run_b.messages = [*seeded_b, Message(role=Role.USER, content="from b")]

    conversation.record(run_a)
    conversation.record(run_b)

    contents = [m.content for m in conversation.messages]
    assert contents == ["from b"]
    assert "from a" not in contents
