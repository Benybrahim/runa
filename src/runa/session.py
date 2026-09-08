"""session.py: `SessionABC`, and the `agent_sessions`/`agent_messages` tables inside `runa.db`.

Same file, same connect-and-create-if-missing pattern as `tracing/storage.py` and
`eval/storage/sqlite.py`. `cli/sessions.py` reads these tables directly with raw SQL.

A thin synchronous wrapper: Runa is a single-process, CLI-first framework, so this skips the
thread-local connections, WAL mode, and cross-process file locking a multi-process-safe session
store would need.
"""

import json
import sqlite3
from abc import ABC, abstractmethod
from contextlib import closing
from pathlib import Path

from runa._sqlite import DEFAULT_DB_PATH
from runa._sqlite import connect as _connect_db
from runa._types import TResponseInputItem

_SESSIONS_TABLE = "agent_sessions"
_MESSAGES_TABLE = "agent_messages"

_DDL = f"""
CREATE TABLE IF NOT EXISTS {_SESSIONS_TABLE} (
    session_id TEXT PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS {_MESSAGES_TABLE} (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES {_SESSIONS_TABLE}(session_id) ON DELETE CASCADE,
    message_data TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_{_MESSAGES_TABLE}_session_id ON {_MESSAGES_TABLE} (session_id, id);
"""


class SessionABC(ABC):
    """What `_runner.py` needs to persist and replay conversation history across turns."""

    session_id: str

    @abstractmethod
    async def get_items(self, limit: int | None = None) -> list[TResponseInputItem]:
        """Return this session's items, oldest first, capped at the latest `limit` if given."""

    @abstractmethod
    async def add_items(self, items: list[TResponseInputItem]) -> None:
        """Append `items` to this session's history."""

    @abstractmethod
    async def pop_item(self) -> TResponseInputItem | None:
        """Remove and return this session's most recent item, or `None` if it has none."""

    @abstractmethod
    async def clear_session(self) -> None:
        """Delete this session and all of its items."""


class SQLiteSession(SessionABC):
    """Conversation history for one `session_id`, persisted to `runa.db`."""

    def __init__(self, session_id: str, db_path: str | Path = DEFAULT_DB_PATH) -> None:
        """Store `session_id` and where in `runa.db` its history lives."""
        self.session_id = session_id
        self.db_path = Path(db_path)

    def _connect(self) -> sqlite3.Connection:
        return _connect_db(self.db_path, _DDL)

    async def get_items(self, limit: int | None = None) -> list[TResponseInputItem]:
        """Return this session's items, oldest first, capped at the latest `limit` if given."""
        with closing(self._connect()) as conn:
            if limit is None:
                rows = conn.execute(
                    f"SELECT message_data FROM {_MESSAGES_TABLE} WHERE session_id = ? ORDER BY id",
                    (self.session_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    f"""
                    SELECT message_data FROM {_MESSAGES_TABLE} WHERE session_id = ?
                    ORDER BY id DESC LIMIT ?
                    """,
                    (self.session_id, limit),
                ).fetchall()
                rows.reverse()
        return [json.loads(row[0]) for row in rows]

    async def add_items(self, items: list[TResponseInputItem]) -> None:
        """Append `items`, creating the session row on first write."""
        if not items:
            return
        with closing(self._connect()) as conn:
            conn.execute(
                f"INSERT OR IGNORE INTO {_SESSIONS_TABLE} (session_id) VALUES (?)",
                (self.session_id,),
            )
            conn.executemany(
                f"INSERT INTO {_MESSAGES_TABLE} (session_id, message_data) VALUES (?, ?)",
                [(self.session_id, json.dumps(item)) for item in items],
            )
            conn.execute(
                f"UPDATE {_SESSIONS_TABLE} SET updated_at = CURRENT_TIMESTAMP WHERE session_id = ?",
                (self.session_id,),
            )
            conn.commit()

    async def pop_item(self) -> TResponseInputItem | None:
        """Remove and return this session's most recent item, or `None` if it has none."""
        with closing(self._connect()) as conn:
            row = conn.execute(
                f"""
                DELETE FROM {_MESSAGES_TABLE}
                WHERE id = (
                    SELECT id FROM {_MESSAGES_TABLE} WHERE session_id = ? ORDER BY id DESC LIMIT 1
                )
                RETURNING message_data
                """,
                (self.session_id,),
            ).fetchone()
            conn.commit()
        return json.loads(row[0]) if row else None

    async def clear_session(self) -> None:
        """Delete this session and all of its items."""
        with closing(self._connect()) as conn:
            conn.execute(f"DELETE FROM {_MESSAGES_TABLE} WHERE session_id = ?", (self.session_id,))
            conn.execute(f"DELETE FROM {_SESSIONS_TABLE} WHERE session_id = ?", (self.session_id,))
            conn.commit()


__all__ = ["SQLiteSession", "SessionABC"]
