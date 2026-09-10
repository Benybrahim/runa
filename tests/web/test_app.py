"""Tests for `runa.web.app`: every `runa ui` route, over a scaffolded project."""

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from runa.cli.generate import generate_agent
from runa.cli.new import scaffold_project
from runa.eval.case import Case
from runa.eval.evaluation.core import EvaluationResult, Status
from runa.eval.report import CaseReport, Report
from runa.eval.storage import save_report
from runa.eval.tracing.adapter import AgentRun
from runa.session import SQLiteSession
from runa.tracing.spans import Span
from runa.tracing.storage import save_trace
from runa.tracing.traces import Trace
from runa.web.app import create_app


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """A scaffolded project with one agent, one session, one trace, and one eval run."""
    project_dir = scaffold_project("demo", root=tmp_path)
    generate_agent("Support", root=project_dir)
    db_path = project_dir / "db" / "runa.db"

    session = SQLiteSession("support_agent-1", db_path=db_path)
    asyncio.run(session.add_items([{"role": "user", "content": "hi there"}]))

    trace = Trace(id="trace_1", name="support_agent", start_time=0.0, end_time=1.0)
    trace.spans = [
        Span(
            id="s1",
            trace_id="trace_1",
            parent_id=None,
            name="turn",
            type="agent",
            start_time=0.0,
            end_time=1.0,
            status="error",
            error="boom",
        )
    ]
    save_trace(trace, db_path=db_path)

    save_report(
        Report(
            agent_name="support_agent",
            cases=[
                CaseReport(
                    index=0,
                    case=Case(input="hi", expected="hi"),
                    run=AgentRun(input="hi", final_output="hi"),
                    results=[
                        EvaluationResult(
                            metric="task_completion", status=Status.PASS, reason="ok", score=1.0
                        )
                    ],
                )
            ],
        ),
        db_path=db_path,
    )
    return project_dir


@pytest.fixture
def client(project: Path) -> TestClient:
    """A `TestClient` for `create_app(project)`."""
    return TestClient(create_app(project))


def test_index_redirects_to_agents(client: TestClient) -> None:
    """`/` redirects to `/agents`, the dashboard's landing page."""
    response = client.get("/", follow_redirects=False)

    assert response.status_code in (302, 307)
    assert response.headers["location"] == "/agents"


def test_agents_page_lists_declared_agents(client: TestClient) -> None:
    """`/agents` shows every declared Agent subclass."""
    response = client.get("/agents")

    assert response.status_code == 200
    assert "support_agent" in response.text


def test_agents_page_reports_a_clean_error_outside_a_runa_project(tmp_path: Path) -> None:
    """`/agents` returns 400 (not a 500 traceback) when `root` isn't a Runa project."""
    response = TestClient(create_app(tmp_path)).get("/agents")

    assert response.status_code == 400


def test_sessions_list_and_detail(client: TestClient) -> None:
    """`/sessions` lists the session; `/sessions/{id}` renders its messages."""
    listing = client.get("/sessions")
    assert "support_agent-1" in listing.text

    detail = client.get("/sessions/support_agent-1")
    assert detail.status_code == 200
    assert "hi there" in detail.text


def test_session_detail_404s_for_an_unknown_session(client: TestClient) -> None:
    """`/sessions/{id}` returns 404 for a session id with no history."""
    assert client.get("/sessions/nope").status_code == 404


def test_traces_list_and_detail(client: TestClient) -> None:
    """`/traces` lists the trace; `?status=error` filters to it; the detail shows the error."""
    listing = client.get("/traces")
    assert "support_agent" in listing.text

    errors_only = client.get("/traces", params={"status": "error"})
    assert "trace_1" in errors_only.text

    detail = client.get("/traces/trace_1")
    assert detail.status_code == 200
    assert "boom" in detail.text


def test_trace_detail_404s_for_an_unknown_trace(client: TestClient) -> None:
    """`/traces/{id}` returns 404 for a trace id `db/runa.db` has no record of."""
    assert client.get("/traces/nope").status_code == 404


def test_evaluations_list_and_detail(client: TestClient) -> None:
    """`/evaluations` lists the run; `/evaluations/{id}` shows its per-case results."""
    listing = client.get("/evaluations")
    assert "support_agent" in listing.text

    detail = client.get("/evaluations/1")
    assert detail.status_code == 200
    assert "task_completion" in detail.text


def test_evaluation_detail_404s_for_an_unknown_run(client: TestClient) -> None:
    """`/evaluations/{id}` returns 404 for an `eval_runs.id` that doesn't exist."""
    assert client.get("/evaluations/999").status_code == 404
