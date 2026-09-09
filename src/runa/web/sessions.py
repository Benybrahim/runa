"""web/sessions.py: the Sessions pages -- conversation transcripts from `db/runa.db`.

Data comes from `runa.cli.sessions` (`session_rows`/`session_messages`); this module only turns
those into HTML.
"""

from pathlib import Path

from runa.cli.sessions import SessionNotFound, session_messages, session_rows
from runa.web._html import back_link, empty, escape, page

__all__ = ["SessionNotFound", "render_detail", "render_list"]


def render_list(*, root: Path) -> str:
    """Render `/sessions`: every session id in `db/runa.db`, most recently updated first."""
    rows = list(reversed(session_rows(root=root)))
    if not rows:
        body = empty("no sessions yet -- run `runa chat <agent>` to start one")
    else:
        items = "".join(
            f'<a class="row" href="/sessions/{escape(session_id)}">'
            f'<span class="primary">{escape(session_id)}</span>'
            f'<span class="meta">{escape(updated_at)}</span></a>'
            for session_id, updated_at in rows
        )
        body = f'<div class="list">{items}</div>'
    return page(
        title="Sessions",
        active="Sessions",
        body=f'<h1>Sessions</h1><p class="subtitle">Conversation history persisted by '
        f"SQLiteSession.</p>{body}",
    )


def render_detail(session_id: str, *, root: Path) -> str:
    """Render `/sessions/{session_id}`: that session's messages as a chat transcript."""
    messages = session_messages(session_id, root=root)
    bubbles = "".join(
        f'<div class="bubble"><div class="role">{escape(message["role"])}</div>'
        f'<div class="text">{escape(message["text"])}</div>'
        f'<div class="time">{escape(message["created_at"])}</div></div>'
        for message in messages
    )
    body = (
        back_link("/sessions", "sessions")
        + f"<h1>{escape(session_id)}</h1>"
        + (bubbles or empty("no messages"))
    )
    return page(title=session_id, active="Sessions", body=body)
