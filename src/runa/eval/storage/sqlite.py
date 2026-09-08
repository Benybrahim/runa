"""eval/storage/sqlite.py: the `eval_runs`/`eval_cases` tables inside `runa.db`.

Every `agent.evaluate()` call writes one row to `eval_runs` (one "experiment") and one row
per case to `eval_cases`, in the same `runa.db` file `SQLiteSession` and the pending-approvals
table already use (see `cli/_approvals.py`), so a local app accumulates one database with no setup.
"""

import json
import sqlite3
from contextlib import closing
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from runa.eval.report import Report

_RUNS_TABLE = "eval_runs"
_CASES_TABLE = "eval_cases"

DEFAULT_DB_PATH = Path("runa.db")


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_RUNS_TABLE} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            score REAL NOT NULL,
            pass_rate REAL NOT NULL
        )
        """
    )
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_CASES_TABLE} (
            run_id INTEGER NOT NULL REFERENCES {_RUNS_TABLE}(id),
            case_index INTEGER NOT NULL,
            input TEXT NOT NULL,
            output TEXT,
            passed INTEGER NOT NULL,
            results_json TEXT NOT NULL,
            PRIMARY KEY (run_id, case_index)
        )
        """
    )
    conn.commit()
    return conn


def save_report(report: Report, *, db_path: Path = DEFAULT_DB_PATH) -> int:
    """Persist `report` to `db_path`, returning the new `eval_runs.id`."""
    created_at = datetime.now(UTC).isoformat()
    with closing(_connect(db_path)) as conn:
        cursor = conn.execute(
            f"INSERT INTO {_RUNS_TABLE} (agent_name, created_at, score, pass_rate) "
            "VALUES (?, ?, ?, ?)",
            (report.agent_name, created_at, report.score, report.pass_rate),
        )
        run_id = cursor.lastrowid
        assert run_id is not None
        conn.executemany(
            f"""
            INSERT INTO {_CASES_TABLE}
                (run_id, case_index, input, output, passed, results_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    run_id,
                    case.index,
                    case.run.input,
                    case.run.final_output,
                    int(case.passed),
                    json.dumps([asdict(result) for result in case.results], default=str),
                )
                for case in report.cases
            ],
        )
        conn.commit()
    return run_id
