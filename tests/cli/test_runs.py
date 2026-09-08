"""Tests for `runa.cli.runs`: show/list/pending/approve/deny/cancel over runa.db."""

import asyncio
from pathlib import Path
from typing import Any

import pytest
from agents.items import ToolApprovalItem
from openai.types.responses import ResponseFunctionToolCall

from runa.agent import Agent
from runa.cli import _approvals
from runa.cli.new import scaffold_project
from runa.cli.runs import (
    PendingApprovalNotFound,
    RunNotFound,
    approve_run,
    cancel_pending,
    deny_run,
    list_pending_runs,
    list_sessions,
    show_session,
)
from runa.session import SQLiteSession


def _scaffold_with_support_agent(tmp_path: Path) -> Path:
    project_dir = scaffold_project("demo", root=tmp_path)
    (project_dir / "app" / "agents" / "support_agent.py").write_text(
        "from runa import Agent\n\n\nclass SupportAgent(Agent):\n    name = 'SupportAgent'\n"
    )
    return project_dir


def _add_history(db_path: Path, session_id: str) -> None:
    session = SQLiteSession(session_id, db_path=db_path)
    asyncio.run(session.add_items([{"role": "user", "content": "hello"}]))


def test_list_sessions_reports_none_when_runa_db_is_empty(tmp_path: Path) -> None:
    """`list_sessions` reports no sessions when `runa.db` has no history yet."""
    project_dir = scaffold_project("demo", root=tmp_path)

    assert list_sessions(root=project_dir) == "no sessions found"


def test_list_sessions_flags_a_session_awaiting_approval(tmp_path: Path) -> None:
    """A session with a pending approval is flagged in the listing."""
    project_dir = _scaffold_with_support_agent(tmp_path)
    db_path = project_dir / "runa.db"
    _add_history(db_path, "SupportAgent")
    agent = Agent(name="SupportAgent")
    interruption = ToolApprovalItem(
        agent=agent,
        raw_item=ResponseFunctionToolCall(
            call_id="call_1", name="delete_file", arguments="{}", type="function_call"
        ),
    )
    _approvals.save_pending(
        db_path,
        session_id="SupportAgent",
        agent_class_name="SupportAgent",
        interruptions=[interruption],
        state_json="{}",
    )

    output = list_sessions(root=project_dir)

    assert "SupportAgent" in output
    assert "awaiting approval" in output


def test_show_session_raises_for_an_unknown_session(tmp_path: Path) -> None:
    """`show_session` raises `RunNotFound` for a session id with no history."""
    project_dir = scaffold_project("demo", root=tmp_path)

    with pytest.raises(RunNotFound):
        show_session("nope", root=project_dir)


def test_show_session_renders_history_and_pending_approvals(tmp_path: Path) -> None:
    """`show_session` renders the session's messages plus any pending approval."""
    project_dir = _scaffold_with_support_agent(tmp_path)
    db_path = project_dir / "runa.db"
    _add_history(db_path, "SupportAgent")
    agent = Agent(name="SupportAgent")
    interruption = ToolApprovalItem(
        agent=agent,
        raw_item=ResponseFunctionToolCall(
            call_id="call_1", name="delete_file", arguments="{}", type="function_call"
        ),
    )
    _approvals.save_pending(
        db_path,
        session_id="SupportAgent",
        agent_class_name="SupportAgent",
        interruptions=[interruption],
        state_json="{}",
    )

    output = show_session("SupportAgent", root=project_dir)

    assert "hello" in output
    assert "delete_file" in output
    assert "call_1" in output


def test_list_pending_runs_reports_none_when_nothing_is_pending(tmp_path: Path) -> None:
    """`list_pending_runs` reports nothing pending when the table is empty."""
    project_dir = scaffold_project("demo", root=tmp_path)

    assert list_pending_runs(root=project_dir) == "no runs awaiting approval"


def test_cancel_pending_raises_when_nothing_is_pending(tmp_path: Path) -> None:
    """`cancel_pending` raises `PendingApprovalNotFound` for a session with nothing pending."""
    project_dir = scaffold_project("demo", root=tmp_path)

    with pytest.raises(PendingApprovalNotFound):
        cancel_pending("SupportAgent", root=project_dir)


def test_cancel_pending_drops_every_row_for_the_session(tmp_path: Path) -> None:
    """`cancel_pending` removes the session's pending rows without resuming its run."""
    project_dir = _scaffold_with_support_agent(tmp_path)
    db_path = project_dir / "runa.db"
    agent = Agent(name="SupportAgent")
    interruption = ToolApprovalItem(
        agent=agent,
        raw_item=ResponseFunctionToolCall(
            call_id="call_1", name="delete_file", arguments="{}", type="function_call"
        ),
    )
    _approvals.save_pending(
        db_path,
        session_id="SupportAgent",
        agent_class_name="SupportAgent",
        interruptions=[interruption],
        state_json="{}",
    )

    result = cancel_pending("SupportAgent", root=project_dir)

    assert "cancelled 1" in result
    assert _approvals.list_pending(db_path, session_id="SupportAgent") == []


class _FakeState:
    """A stand-in for `RunState`, just enough for approve/deny to drive."""

    def __init__(self, interruptions: list[Any]) -> None:
        self._interruptions = interruptions
        self.approved: list[Any] = []
        self.rejected: list[tuple[Any, str | None]] = []

    def get_interruptions(self) -> list[Any]:
        """Return the fixed interruptions this fake state was built with."""
        return self._interruptions

    def approve(self, item: Any, always_approve: bool = False) -> None:
        """Record that `item` was approved."""
        self.approved.append(item)

    def reject(
        self, item: Any, always_reject: bool = False, *, rejection_message: str | None = None
    ) -> None:
        """Record that `item` was rejected, with its rejection message."""
        self.rejected.append((item, rejection_message))

    def to_json(self) -> dict[str, Any]:
        """Return an empty payload, mirroring `RunState.to_json()`."""
        return {}


class _FakeResumedResult:
    """A stand-in for the `RunResult` a resumed run produces."""

    def __init__(self, final_output: str = "done", interruptions: list[Any] | None = None):
        self.final_output = final_output
        self.interruptions = interruptions or []

    def to_state(self) -> _FakeState:
        """Return a state with no further interruptions, mirroring a clean resume."""
        return _FakeState([])


def _setup_pending(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, str]:
    project_dir = _scaffold_with_support_agent(tmp_path)
    db_path = project_dir / "runa.db"
    agent = Agent(name="SupportAgent")
    interruption = ToolApprovalItem(
        agent=agent,
        raw_item=ResponseFunctionToolCall(
            call_id="call_1", name="delete_file", arguments="{}", type="function_call"
        ),
    )
    _approvals.save_pending(
        db_path,
        session_id="SupportAgent",
        agent_class_name="SupportAgent",
        interruptions=[interruption],
        state_json="{}",
    )

    fake_state = _FakeState([interruption])

    async def fake_from_json(agent: Any, state_json: Any) -> _FakeState:
        return fake_state

    monkeypatch.setattr("runa.cli.runs.RunState.from_json", staticmethod(fake_from_json))
    return project_dir, "call_1"


def test_approve_run_raises_for_an_unknown_tool_call_id(tmp_path: Path) -> None:
    """`approve_run` raises `PendingApprovalNotFound` for an id with no pending approval."""
    project_dir = _scaffold_with_support_agent(tmp_path)

    with pytest.raises(PendingApprovalNotFound):
        approve_run("SupportAgent", "call_1", root=project_dir)


def test_approve_run_resumes_and_clears_the_pending_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Approving marks the interruption approved, resumes the run, and clears the pending row."""
    project_dir, tool_call_id = _setup_pending(tmp_path, monkeypatch)
    fake_state_holder: dict[str, _FakeState] = {}

    async def fake_run(agent: Any, state: Any, **kwargs: Any) -> _FakeResumedResult:
        fake_state_holder["state"] = state
        return _FakeResumedResult(final_output="deleted!")

    monkeypatch.setattr("runa.cli.runs.Runner.run", staticmethod(fake_run))

    output = approve_run("SupportAgent", tool_call_id, root=project_dir)

    assert "approved" in output
    assert "deleted!" in output
    assert len(fake_state_holder["state"].approved) == 1
    assert _approvals.list_pending(project_dir / "runa.db", session_id="SupportAgent") == []


def test_deny_run_passes_the_rejection_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Denying rejects the interruption with the given reason, and resumes the run."""
    project_dir, tool_call_id = _setup_pending(tmp_path, monkeypatch)
    fake_state_holder: dict[str, _FakeState] = {}

    async def fake_run(agent: Any, state: Any, **kwargs: Any) -> _FakeResumedResult:
        fake_state_holder["state"] = state
        return _FakeResumedResult(final_output="stopped.")

    monkeypatch.setattr("runa.cli.runs.Runner.run", staticmethod(fake_run))

    output = deny_run("SupportAgent", tool_call_id, root=project_dir, reason="too risky")

    assert "denied" in output
    rejected_item, rejected_message = fake_state_holder["state"].rejected[0]
    assert rejected_message == "too risky"


def test_approve_run_saves_new_pending_rows_when_still_interrupted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the resumed run pauses again, the new interruptions are persisted in turn."""
    project_dir, tool_call_id = _setup_pending(tmp_path, monkeypatch)
    agent = Agent(name="SupportAgent")
    next_interruption = ToolApprovalItem(
        agent=agent,
        raw_item=ResponseFunctionToolCall(
            call_id="call_2", name="send_email", arguments="{}", type="function_call"
        ),
    )

    async def fake_run(agent: Any, state: Any, **kwargs: Any) -> _FakeResumedResult:
        return _FakeResumedResult(interruptions=[next_interruption])

    monkeypatch.setattr("runa.cli.runs.Runner.run", staticmethod(fake_run))

    output = approve_run("SupportAgent", tool_call_id, root=project_dir)

    assert "still awaiting approval" in output
    pending = _approvals.get_pending(
        project_dir / "runa.db", session_id="SupportAgent", tool_call_id="call_2"
    )
    assert pending is not None
    assert pending.tool_name == "send_email"
