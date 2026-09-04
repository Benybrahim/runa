from datetime import UTC, datetime, timedelta

import pytest

from runa.cli.new import scaffold_project
from runa.cli.runs import (
    RunNotFound,
    approve_run,
    cancel_run,
    deny_run,
    list_pending_runs,
    list_runs,
    show_run,
)
from runa.core import IllegalTransition, Message, Role, Run, RunStatus, ToolCall
from runa.persistence import SQLiteRunStore

_MAIN_PY_TEMPLATE = """
from runa import configure
from runa.persistence import SQLiteRunStore
from tests.fakes import FakeProvider

configure(
    provider=FakeProvider(responses=[]),
    run_store=SQLiteRunStore({db_path!r}),
)
"""


def _scaffold_with_store(tmp_path):
    project_dir = scaffold_project("acme", root=tmp_path)
    db_path = str(tmp_path / "runs.db")
    (project_dir / "main.py").write_text(_MAIN_PY_TEMPLATE.format(db_path=db_path))
    return project_dir, db_path


def test_show_run_renders_a_saved_runs_timeline(tmp_path):
    project_dir, db_path = _scaffold_with_store(tmp_path)
    store = SQLiteRunStore(db_path)
    run = Run(input="hello")
    run.start()
    run.complete(result="hi")
    store.save(run)
    store.close()

    output = show_run(run.id, root=project_dir)

    assert run.id in output
    assert "run started" in output
    assert "run completed" in output


def test_show_run_notes_delegation_when_the_run_has_a_parent(tmp_path):
    project_dir, db_path = _scaffold_with_store(tmp_path)
    store = SQLiteRunStore(db_path)
    parent = Run(input="parent")
    parent.start()
    parent.complete(result="done")
    child = Run(input="child", parent_run_id=parent.id)
    child.start()
    child.complete(result="done")
    store.save(parent)
    store.save(child)
    store.close()

    output = show_run(child.id, root=project_dir)

    assert parent.id in output


def test_show_run_raises_for_an_unknown_id(tmp_path):
    project_dir, _ = _scaffold_with_store(tmp_path)

    with pytest.raises(RunNotFound):
        show_run("does-not-exist", root=project_dir)


def test_show_run_does_not_discover_a_run_that_executed_but_was_never_saved(tmp_path):
    """A Run that ran in-process (`timeline(run)` works on it immediately) is
    not automatically visible to the CLI — only Runs actually persisted to
    the configured RunStore are. Distinct from an unknown/made-up id: this
    Run is real and has a full event history, just never `store.save()`d."""
    project_dir, _ = _scaffold_with_store(tmp_path)
    run = Run(input="hello")
    run.start()
    run.complete(result="hi")

    with pytest.raises(RunNotFound):
        show_run(run.id, root=project_dir)


def test_list_runs_shows_every_saved_run(tmp_path):
    project_dir, db_path = _scaffold_with_store(tmp_path)
    store = SQLiteRunStore(db_path)
    completed = Run(input="one")
    completed.start()
    completed.complete(result="done")
    store.save(completed)
    store.close()

    output = list_runs(root=project_dir)

    assert completed.id in output
    assert "completed" in output


def test_list_runs_filters_by_status(tmp_path):
    project_dir, db_path = _scaffold_with_store(tmp_path)
    store = SQLiteRunStore(db_path)
    completed = Run(input="one")
    completed.start()
    completed.complete(result="done")
    failed = Run(input="two")
    failed.start()
    failed.fail("boom")
    store.save(completed)
    store.save(failed)
    store.close()

    output = list_runs(root=project_dir, status="failed")

    assert failed.id in output
    assert completed.id not in output


def test_list_runs_filters_by_agent_name(tmp_path):
    project_dir, db_path = _scaffold_with_store(tmp_path)
    store = SQLiteRunStore(db_path)
    research = Run(input="one", agent_name="ResearchAgent")
    support = Run(input="two", agent_name="SupportAgent")
    store.save(research)
    store.save(support)
    store.close()

    output = list_runs(root=project_dir, agent_name="ResearchAgent")

    assert research.id in output
    assert support.id not in output


def test_list_runs_filters_by_parent_run_id(tmp_path):
    project_dir, db_path = _scaffold_with_store(tmp_path)
    store = SQLiteRunStore(db_path)
    parent = Run(input="parent")
    child = Run(input="child", parent_run_id=parent.id)
    other = Run(input="unrelated")
    store.save(parent)
    store.save(child)
    store.save(other)
    store.close()

    output = list_runs(root=project_dir, parent_run_id=parent.id)

    assert child.id in output
    assert other.id not in output
    assert parent.id not in output


def test_list_runs_filters_by_since(tmp_path):
    project_dir, db_path = _scaffold_with_store(tmp_path)
    store = SQLiteRunStore(db_path)
    old = Run(input="old", created_at=datetime.now(UTC) - timedelta(days=1))
    recent = Run(input="recent")
    store.save(old)
    store.save(recent)
    store.close()

    since = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    output = list_runs(root=project_dir, since=since)

    assert recent.id in output
    assert old.id not in output


def test_list_runs_is_empty_with_no_saved_runs(tmp_path):
    project_dir, _ = _scaffold_with_store(tmp_path)

    assert list_runs(root=project_dir) == "no runs found"


def _save_awaiting_approval(store: SQLiteRunStore) -> tuple[Run, ToolCall]:
    call = ToolCall(name="SendEmail", arguments={"to": "a@example.com"})
    run = Run(input="email someone")
    run.start()
    run.add_message(Message(role=Role.ASSISTANT, tool_calls=[call]))
    run.require_approval(call.id)
    store.save(run)
    return run, call


def test_list_pending_runs_shows_a_run_awaiting_approval(tmp_path):
    project_dir, db_path = _scaffold_with_store(tmp_path)
    store = SQLiteRunStore(db_path)
    run, call = _save_awaiting_approval(store)
    store.close()

    output = list_pending_runs(root=project_dir)

    assert run.id in output
    assert call.id in output
    assert "SendEmail" in output


def test_list_pending_runs_is_empty_with_no_awaiting_runs(tmp_path):
    project_dir, _ = _scaffold_with_store(tmp_path)

    assert list_pending_runs(root=project_dir) == "no runs awaiting approval"


def test_list_pending_runs_reports_the_gated_call_not_an_earlier_completed_one(
    tmp_path,
):
    """An earlier, ordinary tool call also has `approved is None` — the
    pending-call lookup must not mistake it for the one actually gating
    approval (see `_pending_tool_call`)."""
    project_dir, db_path = _scaffold_with_store(tmp_path)
    store = SQLiteRunStore(db_path)

    search_call = ToolCall(name="SearchKB", arguments={"query": "refund policy"})
    search_call.attempts = 1
    transfer_call = ToolCall(name="TransferFunds", arguments={"amount": 5000})
    run = Run(input="handle the refund")
    run.start()
    run.add_message(Message(role=Role.ASSISTANT, tool_calls=[search_call]))
    run.add_message(
        Message(role=Role.TOOL, content="found it", tool_call_id=search_call.id)
    )
    run.add_message(Message(role=Role.ASSISTANT, tool_calls=[transfer_call]))
    run.require_approval(transfer_call.id)
    store.save(run)
    store.close()

    output = list_pending_runs(root=project_dir)

    assert "TransferFunds" in output
    assert transfer_call.id in output
    assert "SearchKB" not in output


def test_approve_run_resumes_and_persists_the_run(tmp_path):
    project_dir, db_path = _scaffold_with_store(tmp_path)
    store = SQLiteRunStore(db_path)
    run, call = _save_awaiting_approval(store)
    store.close()

    output = approve_run(run.id, call.id, root=project_dir)

    assert "approved" in output
    store = SQLiteRunStore(db_path)
    saved = store.get(run.id)
    store.close()
    assert saved.status == RunStatus.RUNNING
    assert saved.tool_calls[0].approved is True


def test_deny_run_fails_and_persists_the_run(tmp_path):
    project_dir, db_path = _scaffold_with_store(tmp_path)
    store = SQLiteRunStore(db_path)
    run, call = _save_awaiting_approval(store)
    store.close()

    output = deny_run(run.id, call.id, root=project_dir, reason="not authorized")

    assert "denied" in output
    store = SQLiteRunStore(db_path)
    saved = store.get(run.id)
    store.close()
    assert saved.status == RunStatus.FAILED
    assert saved.tool_calls[0].approved is False
    assert "not authorized" in saved.events[-1].data["error"]


def test_approve_run_raises_for_an_unknown_id(tmp_path):
    project_dir, _ = _scaffold_with_store(tmp_path)

    with pytest.raises(RunNotFound):
        approve_run("does-not-exist", "some-call", root=project_dir)


def test_cancel_run_cancels_and_persists_a_paused_run(tmp_path):
    project_dir, db_path = _scaffold_with_store(tmp_path)
    store = SQLiteRunStore(db_path)
    run, _call = _save_awaiting_approval(store)
    store.close()

    output = cancel_run(run.id, root=project_dir)

    assert "cancelled" in output
    store = SQLiteRunStore(db_path)
    saved = store.get(run.id)
    store.close()
    assert saved.status == RunStatus.CANCELLED


def test_cancel_run_raises_for_an_unknown_id(tmp_path):
    project_dir, _ = _scaffold_with_store(tmp_path)

    with pytest.raises(RunNotFound):
        cancel_run("does-not-exist", root=project_dir)


def test_cancel_run_raises_for_an_already_terminal_run(tmp_path):
    project_dir, db_path = _scaffold_with_store(tmp_path)
    store = SQLiteRunStore(db_path)
    run = Run(input="one")
    run.start()
    run.complete(result="done")
    store.save(run)
    store.close()

    with pytest.raises(IllegalTransition):
        cancel_run(run.id, root=project_dir)
