from runa.core import Conversation
from runa.persistence import ConversationStore, InMemoryConversationStore


def test_save_and_get_round_trips_a_conversation():
    store = InMemoryConversationStore()
    conversation = Conversation()

    store.save(conversation)

    assert store.get(conversation.id) is conversation


def test_get_missing_conversation_returns_none():
    store = InMemoryConversationStore()

    assert store.get("does-not-exist") is None


def test_list_returns_all_saved_conversations():
    store = InMemoryConversationStore()
    first = Conversation()
    second = Conversation()

    store.save(first)
    store.save(second)

    assert {c.id for c in store.list()} == {first.id, second.id}


def test_conversation_store_protocol_is_satisfiable_without_inheritance():
    class DictBackedStore:
        def __init__(self):
            self._conversations = {}

        def save(self, conversation):
            self._conversations[conversation.id] = conversation

        def get(self, conversation_id):
            return self._conversations.get(conversation_id)

        def list(self):
            return list(self._conversations.values())

    store: ConversationStore = DictBackedStore()
    conversation = Conversation()
    store.save(conversation)

    assert store.get(conversation.id) is conversation
    assert store.list() == [conversation]
