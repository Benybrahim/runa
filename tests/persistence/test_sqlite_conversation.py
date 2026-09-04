import threading

from runa.core import Conversation, Message, Role, TextArtifact, ToolCall
from runa.persistence import SQLiteConversationStore


def test_save_and_get_round_trips_a_conversation():
    store = SQLiteConversationStore(":memory:")
    conversation = Conversation()
    conversation.state.topic = "refunds"

    store.save(conversation)
    loaded = store.get(conversation.id)

    assert loaded is not conversation
    assert loaded.id == conversation.id
    assert loaded.state.topic == "refunds"


def test_round_trips_state_with_a_non_json_safe_value():
    store = SQLiteConversationStore(":memory:")
    conversation = Conversation()
    artifact = TextArtifact(text="a finding")
    conversation.state.findings = [artifact]

    store.save(conversation)
    loaded = store.get(conversation.id)

    assert loaded.state.findings == str([artifact])


def test_get_missing_conversation_returns_none():
    store = SQLiteConversationStore(":memory:")

    assert store.get("does-not-exist") is None


def test_list_returns_all_saved_conversations():
    store = SQLiteConversationStore(":memory:")
    first = Conversation()
    second = Conversation()

    store.save(first)
    store.save(second)

    assert {c.id for c in store.list()} == {first.id, second.id}


def test_save_again_overwrites_the_previous_version():
    store = SQLiteConversationStore(":memory:")
    conversation = Conversation()
    store.save(conversation)

    conversation.messages.append(Message(role=Role.USER, content="hi"))
    store.save(conversation)

    assert len(store.get(conversation.id).messages) == 1
    assert len(store.list()) == 1


def test_survives_reopening_the_same_database_file(tmp_path):
    path = str(tmp_path / "conversations.sqlite3")
    conversation = Conversation()
    conversation.messages.append(Message(role=Role.USER, content="hi"))

    first_connection = SQLiteConversationStore(path)
    first_connection.save(conversation)
    first_connection.close()

    second_connection = SQLiteConversationStore(path)
    loaded = second_connection.get(conversation.id)

    assert loaded.id == conversation.id
    assert loaded.messages[0].content == "hi"


def test_concurrent_save_and_get_from_multiple_threads_does_not_corrupt_data():
    # Same concern as SQLiteRunStore: check_same_thread=False alone doesn't
    # make a shared Connection safe under real thread overlap.
    store = SQLiteConversationStore(":memory:")
    conversations = [Conversation() for _ in range(20)]
    for conversation in conversations:
        store.save(conversation)

    errors: list[Exception] = []
    barrier = threading.Barrier(8)

    def hammer(worker_id: int) -> None:
        barrier.wait()
        for i in range(50):
            conversation = conversations[(worker_id * 50 + i) % len(conversations)]
            try:
                store.save(conversation)
                loaded = store.get(conversation.id)
                if loaded is None:
                    raise AssertionError(f"get returned None for {conversation.id}")
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

    threads = [threading.Thread(target=hammer, args=(i,)) for i in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []


def test_round_trips_messages_and_tool_calls():
    store = SQLiteConversationStore(":memory:")
    conversation = Conversation()
    tool_call = ToolCall(name="send_refund", arguments={"order_id": "A123"})
    conversation.messages.append(
        Message(role=Role.ASSISTANT, content="", tool_calls=[tool_call])
    )
    conversation.messages.append(
        Message(role=Role.TOOL, content="refunded", tool_call_id=tool_call.id)
    )

    store.save(conversation)
    loaded = store.get(conversation.id)

    assert loaded.messages[0].tool_calls[0].name == "send_refund"
    assert loaded.messages[0].tool_calls[0].arguments == {"order_id": "A123"}
    assert loaded.messages[1].tool_call_id == tool_call.id
