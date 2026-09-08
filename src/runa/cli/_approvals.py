"""cli/_approvals.py: the `pending_approvals` table inside an app's `runa.db`.

`SQLiteSession` already persists conversation turns (`agent_sessions`/
`agent_messages`) in the same file (see `cli/run.py`); this adds the one
thing a `Session` can't hold: a paused run's full `RunState`, serialized so
`runa runs approve`/`deny` can resume it from a separate process later.

A pause typically has more than one interruption, but they all share one
`RunState` snapshot, so a resume (`clear_pending`) drops every pending row
for its session at once rather than one at a time.
"""

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from agents.items import ToolApprovalItem

from runa._sqlite import connect as _connect_db

_TABLE = "pending_approvals"

_DDL = f"""
CREATE TABLE IF NOT EXISTS {_TABLE} (
    session_id TEXT NOT NULL,
    tool_call_id TEXT NOT NULL,
    agent_class_name TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    arguments TEXT NOT NULL,
    state_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (session_id, tool_call_id)
);
"""


@dataclass
class PendingApproval:
    """One tool call awaiting approval, plus the `RunState` snapshot to resume it from."""

    session_id: str
    tool_call_id: str
    agent_class_name: str
    tool_name: str
    arguments: str
    state_json: str
    created_at: str


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = _connect_db(db_path, _DDL)
    conn.row_factory = sqlite3.Row
    return conn


def save_pending(
    db_path: Path,
    *,
    session_id: str,
    agent_class_name: str,
    interruptions: list[ToolApprovalItem],
    state_json: str,
) -> None:
    """Persist one row per pending interruption, all sharing `state_json`."""
    created_at = datetime.now(UTC).isoformat()
    with closing(_connect(db_path)) as conn:
        conn.executemany(
            f"""
            INSERT OR REPLACE INTO {_TABLE}
                (session_id, tool_call_id, agent_class_name, tool_name, arguments,
                 state_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    session_id,
                    item.call_id or "",
                    agent_class_name,
                    item.name or "",
                    item.arguments or "",
                    state_json,
                    created_at,
                )
                for item in interruptions
            ],
        )
        conn.commit()


def list_pending(db_path: Path, *, session_id: str | None = None) -> list[PendingApproval]:
    """List pending approvals, optionally narrowed to one `session_id`."""
    with closing(_connect(db_path)) as conn:
        if session_id is None:
            rows = conn.execute(f"SELECT * FROM {_TABLE} ORDER BY created_at").fetchall()
        else:
            rows = conn.execute(
                f"SELECT * FROM {_TABLE} WHERE session_id = ? ORDER BY created_at",
                (session_id,),
            ).fetchall()
    return [PendingApproval(**dict(row)) for row in rows]


def get_pending(db_path: Path, *, session_id: str, tool_call_id: str) -> PendingApproval | None:
    """Look up one pending approval by session and tool_call_id."""
    for pending in list_pending(db_path, session_id=session_id):
        if pending.tool_call_id == tool_call_id:
            return pending
    return None


def clear_pending(db_path: Path, *, session_id: str) -> None:
    """Drop every pending row for `session_id`, once its `RunState` is resumed or abandoned."""
    with closing(_connect(db_path)) as conn:
        conn.execute(f"DELETE FROM {_TABLE} WHERE session_id = ?", (session_id,))
        conn.commit()
