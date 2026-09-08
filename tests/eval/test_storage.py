"""Tests for `runa.eval.storage.sqlite`: `save_report`."""

import json
import sqlite3
from pathlib import Path

from runa.eval.case import Case
from runa.eval.evaluation.core import EvaluationResult, Status
from runa.eval.report import CaseReport, Report
from runa.eval.storage.sqlite import save_report
from runa.eval.tracing.adapter import AgentRun


def test_save_report_persists_a_run_and_its_cases(tmp_path: Path) -> None:
    """`save_report` writes one `runa_eval_runs` row and one `runa_eval_cases` row per case."""
    db_path = tmp_path / "runa.db"
    case_report = CaseReport(
        index=0,
        case=Case(input="hi", expected="hello"),
        run=AgentRun(input="hi", final_output="hello"),
        results=[
            EvaluationResult(metric="task_completion", status=Status.PASS, reason="ok", score=1.0)
        ],
    )
    report = Report(agent_name="SupportAgent", cases=[case_report])

    run_id = save_report(report, db_path=db_path)

    with sqlite3.connect(db_path) as conn:
        run_row = conn.execute(
            "SELECT agent_name, score, pass_rate FROM runa_eval_runs WHERE id = ?", (run_id,)
        ).fetchone()
        case_row = conn.execute(
            "SELECT input, output, passed, results_json FROM runa_eval_cases WHERE run_id = ?",
            (run_id,),
        ).fetchone()

    assert run_row == ("SupportAgent", 1.0, 1.0)
    assert case_row[0] == "hi"
    assert case_row[1] == "hello"
    assert case_row[2] == 1
    assert json.loads(case_row[3])[0]["metric"] == "task_completion"


def test_save_report_handles_an_empty_dataset(tmp_path: Path) -> None:
    """Saving a report with no cases still records the run row."""
    db_path = tmp_path / "runa.db"
    report = Report(agent_name="SupportAgent", cases=[])

    run_id = save_report(report, db_path=db_path)

    with sqlite3.connect(db_path) as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM runa_eval_cases WHERE run_id = ?", (run_id,)
        ).fetchone()[0]

    assert count == 0
