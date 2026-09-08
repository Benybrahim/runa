"""Tests for `runa.cli.sessions`: list/show over runa.db."""

import asyncio
from pathlib import Path

import pytest

from runa.cli.new import scaffold_project
from runa.cli.sessions import SessionNotFound, list_sessions, list_sessions_for_agent, show_session
from runa.session import SQLiteSession


def _add_history(db_path: Path, session_id: str) -> None:
    session = SQLiteSession(session_id, db_path=db_path)
    asyncio.run(session.add_items([{"role": "user", "content": "hello"}]))


def test_list_sessions_reports_none_when_runa_db_is_empty(tmp_path: Path) -> None:
    """`list_sessions` reports no sessions when `runa.db` has no history yet."""
    project_dir = scaffold_project("demo", root=tmp_path)

    assert list_sessions(root=project_dir) == "no sessions found"


def test_list_sessions_lists_a_session_with_history(tmp_path: Path) -> None:
    """A session with history appears in the listing."""
    project_dir = scaffold_project("demo", root=tmp_path)
    _add_history(project_dir / "runa.db", "SupportAgent")

    assert "SupportAgent" in list_sessions(root=project_dir)


def test_list_sessions_for_agent_matches_prefixed_and_exact_ids(tmp_path: Path) -> None:
    """`list_sessions_for_agent` finds both `Support-<suffix>` chats and a bare `Support` one.

    It ignores sessions belonging to a different agent.
    """
    project_dir = scaffold_project("demo", root=tmp_path)
    db_path = project_dir / "runa.db"
    _add_history(db_path, "Support-20260101-000000-aaaa")
    _add_history(db_path, "Support")
    _add_history(db_path, "OtherAgent-20260101-000000-bbbb")

    sessions = list_sessions_for_agent("Support", root=project_dir)

    ids = [session_id for session_id, _ in sessions]
    assert set(ids) == {"Support-20260101-000000-aaaa", "Support"}


def test_list_sessions_for_agent_reports_none_when_there_is_no_history(tmp_path: Path) -> None:
    """`list_sessions_for_agent` returns an empty list when `runa.db` has no matching session."""
    project_dir = scaffold_project("demo", root=tmp_path)

    assert list_sessions_for_agent("Support", root=project_dir) == []


def test_show_session_raises_for_an_unknown_session(tmp_path: Path) -> None:
    """`show_session` raises `SessionNotFound` for a session id with no history."""
    project_dir = scaffold_project("demo", root=tmp_path)

    with pytest.raises(SessionNotFound):
        show_session("nope", root=project_dir)


def test_show_session_renders_history(tmp_path: Path) -> None:
    """`show_session` renders the session's messages."""
    project_dir = scaffold_project("demo", root=tmp_path)
    _add_history(project_dir / "runa.db", "SupportAgent")

    output = show_session("SupportAgent", root=project_dir)

    assert "hello" in output
