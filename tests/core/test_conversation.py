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

    conversation.record(run.messages)

    assert [m.content for m in conversation.messages] == ["hi", "hello"]


def test_record_excludes_the_system_prompt():
    conversation = Conversation()
    run = Run(input="hi")
    run.add_message(Message(role=Role.SYSTEM, content="be helpful"))
    run.add_message(Message(role=Role.USER, content="hi"))

    conversation.record(run.messages)

    assert [m.role for m in conversation.messages] == [Role.USER]


def test_record_appends_rather_than_replaces():
    conversation = Conversation()
    conversation.messages = [Message(role=Role.USER, content="earlier")]
    run = Run(input="hi")
    run.add_message(Message(role=Role.USER, content="fresh"))

    conversation.record(run.messages)

    assert [m.content for m in conversation.messages] == ["earlier", "fresh"]


def test_record_accumulates_across_successive_runs():
    conversation = Conversation()
    first = Run(input="hi")
    first.add_message(Message(role=Role.USER, content="hi"))
    first.add_message(Message(role=Role.ASSISTANT, content="hello"))
    conversation.record(first.messages)

    second = Run(input="again")
    second.add_message(Message(role=Role.USER, content="again"))
    second.add_message(Message(role=Role.ASSISTANT, content="hi again"))
    conversation.record(second.messages)

    assert [m.content for m in conversation.messages] == [
        "hi",
        "hello",
        "again",
        "hi again",
    ]


def test_concurrent_record_calls_never_tear_or_interleave_messages():
    """Many threads racing `record()` must each contribute one whole Run's
    messages, never a mix of two Runs' messages spliced together. Which
    Run's `record()` runs first is unspecified; that every Run's pair stays
    intact and every Run's turn survives (record() appends, see the
    Conversation docstring's Concurrency section) is what the lock
    guarantees."""
    conversation = Conversation()
    runs = []
    for i in range(20):
        run = Run(input=f"run {i}")
        run.add_message(Message(role=Role.USER, content=f"user-{i}"))
        run.add_message(Message(role=Role.ASSISTANT, content=f"assistant-{i}"))
        runs.append(run)

    threads = [
        threading.Thread(target=conversation.record, args=(run.messages,))
        for run in runs
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    contents = [m.content for m in conversation.messages]
    assert len(contents) == 40
    pairs = [contents[i : i + 2] for i in range(0, 40, 2)]
    for user_message, assistant_message in pairs:
        assert user_message.split("-")[1] == assistant_message.split("-")[1]
    assert {pair[0].split("-")[1] for pair in pairs} == {str(i) for i in range(20)}


def test_concurrent_runs_against_one_conversation_do_not_lose_turns():
    """Two Runs that overlap in time against the same Conversation are not
    merged into one coherent narrative: each Run's own model calls only
    ever see history as of when that call happened (see
    `runtime._shared.model_context`), so neither Run is aware of the
    other's turn while both are in flight. But because `record()` appends
    rather than replaces, neither Run's own turn is silently dropped
    either; both land in `.messages`, in whichever order `record()`
    happened to run."""
    conversation = Conversation()

    run_a = Run(input="a")
    run_a.add_message(Message(role=Role.USER, content="from a"))
    run_b = Run(input="b")
    run_b.add_message(Message(role=Role.USER, content="from b"))

    conversation.record(run_a.messages)
    conversation.record(run_b.messages)

    assert [m.content for m in conversation.messages] == ["from a", "from b"]
