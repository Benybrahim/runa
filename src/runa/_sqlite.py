"""_sqlite.py: shared connect-and-create-if-missing plumbing for `runa.db`.

`tracing/storage.py` and `eval/storage/sqlite.py` each own a different set of tables in the
same file; this only opens the connection and applies each caller's DDL, so the file gets
created lazily regardless of which module writes to it first.
"""

import sqlite3
from pathlib import Path

DEFAULT_DB_PATH = Path("runa.db")


def connect(db_path: Path, ddl: str) -> sqlite3.Connection:
    """Open `db_path`, applying `ddl` (one or more `CREATE TABLE IF NOT EXISTS` statements)."""
    conn = sqlite3.connect(db_path)
    conn.executescript(ddl)
    conn.commit()
    return conn
