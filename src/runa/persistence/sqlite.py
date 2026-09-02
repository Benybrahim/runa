"""SQLiteRunStore: a RunStore that survives a process restart.

Same protocol as InMemoryRunStore — swapping one for the other is a
one-line change at the call site (manifesto: real backends are swapped in
via configuration, not code changes). A Run is stored as a single JSON blob
per row; `status` is pulled out into its own column so it can be filtered
without deserializing every row.
"""

import sqlite3

from runa.core import Run
from runa.persistence.serialize import run_from_json, run_to_json

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    data TEXT NOT NULL
)
"""


class SQLiteRunStore:
    """RunStore backed by a SQLite database at `path` (`:memory:` works too)."""

    def __init__(self, path: str) -> None:
        self._connection = sqlite3.connect(path, check_same_thread=False)
        self._connection.execute(_SCHEMA)
        self._connection.commit()

    def save(self, run: Run) -> None:
        self._connection.execute(
            "INSERT INTO runs (id, status, data) VALUES (?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET status = excluded.status, "
            "data = excluded.data",
            (run.id, run.status.value, run_to_json(run)),
        )
        self._connection.commit()

    def get(self, run_id: str) -> Run | None:
        row = self._connection.execute(
            "SELECT data FROM runs WHERE id = ?", (run_id,)
        ).fetchone()
        return run_from_json(row[0]) if row else None

    def list(self) -> list[Run]:
        rows = self._connection.execute("SELECT data FROM runs").fetchall()
        return [run_from_json(row[0]) for row in rows]

    def close(self) -> None:
        self._connection.close()
