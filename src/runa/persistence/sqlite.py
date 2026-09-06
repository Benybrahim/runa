"""SQLiteRunStore: a RunStore that survives a process restart.

Same protocol as InMemoryRunStore: swapping one for the other is a
one-line change at the call site (manifesto: real backends are swapped in
via configuration, not code changes). A Run is stored as a single JSON blob
per row; `status`, `agent_name`, `parent_run_id`, and `conversation_id` are
pulled out into their own columns so `list()` can filter without
deserializing every row.
"""

import sqlite3
import threading
from collections.abc import Mapping
from datetime import datetime

from runa.core import Artifact, Run, RunStatus
from runa.persistence.serialize import run_from_json, run_to_json

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    agent_name TEXT,
    parent_run_id TEXT,
    conversation_id TEXT,
    data TEXT NOT NULL
)
"""


class SQLiteRunStore:
    """RunStore backed by a SQLite database at `path` (`:memory:` works too).

    `check_same_thread=False` only lifts sqlite3's same-thread check; it does
    not make one Connection object safe to call from multiple threads at
    once (the sqlite3 docs say as much). A background Run store is used from
    exactly that way: a `Queue` worker thread saves a Run while another
    thread lists or reads, so every access below is serialized through
    `self._lock`.

    `artifact_resolver`, if given, maps a stored `Artifact.artifact_type()` tag
    to the class to reconstruct it as, for `Artifact` subclasses this store
    holds that shouldn't be resolved by importing a `module.ClassName` path
    out of the row's own data (see `persistence/serialize.py`). A store this
    application fully controls can rely on the zero-config import fallback
    instead and leave this unset.
    """

    def __init__(
        self,
        path: str,
        *,
        artifact_resolver: Mapping[str, type[Artifact]] | None = None,
    ) -> None:
        self._connection = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.Lock()
        self._artifact_resolver = artifact_resolver
        with self._lock:
            self._connection.execute(_SCHEMA)
            self._connection.commit()

    def save(self, run: Run) -> None:
        with self._lock:
            self._connection.execute(
                "INSERT INTO runs "
                "(id, status, created_at, agent_name, parent_run_id, "
                "conversation_id, data) "
                "VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET status = excluded.status, "
                "created_at = excluded.created_at, agent_name = excluded.agent_name, "
                "parent_run_id = excluded.parent_run_id, "
                "conversation_id = excluded.conversation_id, data = excluded.data",
                (
                    run.id,
                    run.status.value,
                    run.created_at.isoformat(),
                    run.agent_name,
                    run.parent_run_id,
                    run.conversation_id,
                    run_to_json(run),
                ),
            )
            self._connection.commit()

    def get(self, run_id: str) -> Run | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT data FROM runs WHERE id = ?", (run_id,)
            ).fetchone()
        if row is None:
            return None
        return run_from_json(row[0], artifact_resolver=self._artifact_resolver)

    def list(
        self,
        *,
        status: RunStatus | None = None,
        since: datetime | None = None,
        agent_name: str | None = None,
        parent_run_id: str | None = None,
        conversation_id: str | None = None,
    ) -> list[Run]:
        query = "SELECT data FROM runs"
        clauses: list[str] = []
        params: list[str] = []
        if status is not None:
            clauses.append("status = ?")
            params.append(status.value)
        if since is not None:
            clauses.append("created_at >= ?")
            params.append(since.isoformat())
        if agent_name is not None:
            clauses.append("agent_name = ?")
            params.append(agent_name)
        if parent_run_id is not None:
            clauses.append("parent_run_id = ?")
            params.append(parent_run_id)
        if conversation_id is not None:
            clauses.append("conversation_id = ?")
            params.append(conversation_id)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        with self._lock:
            rows = self._connection.execute(query, params).fetchall()
        return [
            run_from_json(row[0], artifact_resolver=self._artifact_resolver)
            for row in rows
        ]

    def close(self) -> None:
        with self._lock:
            self._connection.close()
