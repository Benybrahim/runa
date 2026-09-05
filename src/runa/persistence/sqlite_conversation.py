"""SQLiteConversationStore: a ConversationStore that survives a process restart.

Same protocol as InMemoryConversationStore: swapping one for the other is
a one-line change at the call site (manifesto: real backends are swapped in
via configuration, not code changes). Mirrors SQLiteRunStore (sqlite.py): a
Conversation is stored as a single JSON blob per row.
"""

import sqlite3
import threading

from runa.core import Conversation
from runa.persistence.serialize import conversation_from_json, conversation_to_json

_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    data TEXT NOT NULL
)
"""


class SQLiteConversationStore:
    """ConversationStore backed by a SQLite database at `path` (`:memory:` works).

    `check_same_thread=False` only lifts sqlite3's same-thread check; it
    does not make one Connection object safe to call from multiple threads
    at once (the sqlite3 docs say as much). A Conversation shared across
    Runs can be saved from a background `Queue` worker thread while another
    thread reads it, so every access below is serialized through
    `self._lock`.
    """

    def __init__(self, path: str) -> None:
        self._connection = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock:
            self._connection.execute(_SCHEMA)
            self._connection.commit()

    def save(self, conversation: Conversation) -> None:
        with self._lock:
            self._connection.execute(
                "INSERT INTO conversations (id, data) VALUES (?, ?) "
                "ON CONFLICT(id) DO UPDATE SET data = excluded.data",
                (conversation.id, conversation_to_json(conversation)),
            )
            self._connection.commit()

    def get(self, conversation_id: str) -> Conversation | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT data FROM conversations WHERE id = ?", (conversation_id,)
            ).fetchone()
        return conversation_from_json(row[0]) if row else None

    def list(self) -> list[Conversation]:
        with self._lock:
            rows = self._connection.execute("SELECT data FROM conversations").fetchall()
        return [conversation_from_json(row[0]) for row in rows]

    def close(self) -> None:
        with self._lock:
            self._connection.close()
