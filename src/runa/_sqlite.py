"""_sqlite.py: shared connect-and-create-if-missing plumbing for `db/runa.db`.

`tracing/storage.py` and `eval/storage/sqlite.py` each own a different set of tables in the
same file; this only opens the connection and applies each caller's DDL, so the file (and its
parent `db/`, which `sqlite3.connect` won't create on its own) gets created lazily regardless of
which module writes to it first.
"""

import sqlite3
from pathlib import Path

DEFAULT_DB_PATH = Path("db/runa.db")


def connect(db_path: Path, ddl: str) -> sqlite3.Connection:
    """Open `db_path`, creating its parent directory if needed, applying `ddl`."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(ddl)
    conn.commit()
    return conn
