"""cli/runs.py: `runa runs show/list/pending/approve/deny/cancel` over runa.db.

Session history (`agent_sessions`/`agent_messages`, written by
`SQLiteSession`, see `cli/run.py`) and pending approvals (`cli/_approvals.py`'s
own table) live in the same `runa.db` file; this module only reads and
updates it. Approving or denying resumes the paused `RunState` (see
`cli/_approvals.py`) by calling `Runner.run()` again, exactly like resuming
any other paused run: there's no separate "approval" execution path.
"""

import asyncio
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from agents import Runner, RunState

from runa.agent import _RUN_CONFIG, _default_hooks
from runa.cli import _approvals
from runa.cli._project import loaded_app
from runa.cli.run import _require_agents_dir, find_agent_class
from runa.session import SQLiteSession


class RunNotFound(Exception):
    """Raised when a `runa runs` command names a session id `runa.db` has no history for."""


class PendingApprovalNotFound(Exception):
    """Raised when `approve`/`deny`/`cancel` names a call or session with no pending approval."""


def _db_path(root: Path) -> Path:
    return root / "runa.db"


def _format_item(item: dict[str, Any]) -> str:
    role = item.get("role") or item.get("type", "item")
    content = item.get("content")
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        parts = [part["text"] for part in content if isinstance(part, dict) and "text" in part]
        text = "".join(parts) if parts else str(content)
    else:
        text = str(item)
    return f"{role}: {text}"


def list_sessions(*, root: Path) -> str:
    """List every session id `runa.db` has conversation history for."""
    db_path = _db_path(root)
    with closing(sqlite3.connect(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT session_id, updated_at FROM agent_sessions ORDER BY updated_at"
            ).fetchall()
        except sqlite3.OperationalError:
            rows = []
    if not rows:
        return "no sessions found"

    pending_ids = {pending.session_id for pending in _approvals.list_pending(db_path)}
    lines = [
        f"{row['session_id']}  {row['updated_at']}"
        + ("  (awaiting approval)" if row["session_id"] in pending_ids else "")
        for row in rows
    ]
    return "\n".join(lines)


def show_session(session_id: str, *, root: Path) -> str:
    """Render a session's message history, plus any pending approvals."""
    db_path = _db_path(root)
    with closing(sqlite3.connect(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        try:
            exists = conn.execute(
                "SELECT 1 FROM agent_sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        except sqlite3.OperationalError:
            exists = None
        if exists is None:
            raise RunNotFound(f"no session found with id {session_id!r}")
        rows = conn.execute(
            "SELECT message_data, created_at FROM agent_messages WHERE session_id = ? ORDER BY id",
            (session_id,),
        ).fetchall()

    lines = [f"session {session_id}", ""]
    for row in rows:
        lines.append(f"{row['created_at']}  {_format_item(json.loads(row['message_data']))}")

    pending = _approvals.list_pending(db_path, session_id=session_id)
    if pending:
        lines.append("\nawaiting approval:")
        lines.extend(
            f"  {item.tool_name}({item.arguments})  tool_call_id={item.tool_call_id}"
            for item in pending
        )
    return "\n".join(lines)


def list_pending_runs(*, root: Path) -> str:
    """Render every pending approval across every session."""
    pending = _approvals.list_pending(_db_path(root))
    if not pending:
        return "no runs awaiting approval"
    return "\n".join(
        f"{item.session_id}  {item.tool_name}({item.arguments})  tool_call_id={item.tool_call_id}"
        for item in pending
    )


async def _resolve(
    session_id: str, tool_call_id: str, *, root: Path, approve: bool, reason: str = ""
) -> str:
    db_path = _db_path(root)
    pending = _approvals.get_pending(db_path, session_id=session_id, tool_call_id=tool_call_id)
    if pending is None:
        raise PendingApprovalNotFound(
            f"no pending approval for tool_call_id {tool_call_id!r} on session {session_id!r}"
        )

    agents_dir = _require_agents_dir(root)
    with loaded_app(root):
        agent_cls = find_agent_class(pending.agent_class_name, agents_dir=agents_dir)
        agent = agent_cls()
        state = await RunState.from_json(agent, json.loads(pending.state_json))
        target = next(
            (item for item in state.get_interruptions() if item.call_id == tool_call_id), None
        )
        if target is None:
            raise PendingApprovalNotFound(
                f"tool_call_id {tool_call_id!r} is no longer pending on session {session_id!r}"
            )
        if approve:
            state.approve(target)
        else:
            state.reject(target, rejection_message=reason or None)

        _approvals.clear_pending(db_path, session_id=session_id)
        session = SQLiteSession(session_id, db_path=db_path)
        result = await Runner.run(
            agent, state, hooks=_default_hooks(), run_config=_RUN_CONFIG, session=session
        )

    verb = "approved" if approve else "denied"
    if result.interruptions:
        _approvals.save_pending(
            db_path,
            session_id=session_id,
            agent_class_name=agent_cls.__name__,
            interruptions=result.interruptions,
            state_json=json.dumps(result.to_state().to_json()),
        )
        return (
            f"{verb} {tool_call_id}, still awaiting approval on "
            f"{len(result.interruptions)} more call(s)"
        )
    return f"{verb} {tool_call_id}\n{result.final_output}"


def approve_run(session_id: str, tool_call_id: str, *, root: Path) -> str:
    """Approve a pending tool call and resume its run."""
    return asyncio.run(_resolve(session_id, tool_call_id, root=root, approve=True))


def deny_run(session_id: str, tool_call_id: str, *, root: Path, reason: str = "") -> str:
    """Deny a pending tool call and resume its run (typically ending it with a tool error)."""
    return asyncio.run(_resolve(session_id, tool_call_id, root=root, approve=False, reason=reason))


def cancel_pending(session_id: str, *, root: Path) -> str:
    """Abandon every pending approval for `session_id`, without resuming its run."""
    db_path = _db_path(root)
    pending = _approvals.list_pending(db_path, session_id=session_id)
    if not pending:
        raise PendingApprovalNotFound(f"no pending approval for session {session_id!r}")
    _approvals.clear_pending(db_path, session_id=session_id)
    return f"cancelled {len(pending)} pending approval(s) for session {session_id!r}"
