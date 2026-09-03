"""ConversationStore: makes Conversation history and state durable.

Mirrors RunStore (store.py) — a Conversation spans separate `Agent.run()`
calls the way a paused Run spans separate Executor invocations, so it
needs the same "look it up again later" durability.
"""

from typing import Protocol

from runa.core import Conversation


class ConversationStore(Protocol):
    def save(self, conversation: Conversation) -> None: ...
    def get(self, conversation_id: str) -> Conversation | None: ...
    def list(self) -> list[Conversation]: ...


class InMemoryConversationStore:
    """Default ConversationStore: keeps Conversations in a process-local dict.

    This is the development default (manifesto: real backends are swapped
    in via configuration, not code changes) — nothing here survives a
    process restart.
    """

    def __init__(self) -> None:
        self._conversations: dict[str, Conversation] = {}

    def save(self, conversation: Conversation) -> None:
        self._conversations[conversation.id] = conversation

    def get(self, conversation_id: str) -> Conversation | None:
        return self._conversations.get(conversation_id)

    def list(self) -> list[Conversation]:
        return list(self._conversations.values())
