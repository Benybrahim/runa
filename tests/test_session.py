"""Tests for `runa.session.SQLiteSession`."""

import asyncio
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from runa.session import SQLiteSession


def test_add_items_then_get_items_round_trips_in_order(tmp_path: Path) -> None:
    """Items come back oldest-first, matching the order they were added in."""
    session = SQLiteSession("s1", db_path=tmp_path / "runa.db")

    async def _run():
        await session.add_items([{"role": "user", "content": "hi"}])
        await session.add_items([{"role": "assistant", "content": "hello"}])
        return await session.get_items()

    items = asyncio.run(_run())
    assert items == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]


def test_get_items_with_limit_returns_the_latest_n_in_order(tmp_path: Path) -> None:
    """`limit` returns the most recent items, still oldest-first."""
    session = SQLiteSession("s1", db_path=tmp_path / "runa.db")

    async def _run() -> list[Any]:
        for i in range(3):
            await session.add_items([{"role": "user", "content": str(i)}])
        return await session.get_items(limit=2)

    items = asyncio.run(_run())
    assert [item["content"] for item in items] == ["1", "2"]


def test_pop_item_removes_and_returns_the_most_recent_item(tmp_path: Path) -> None:
    """`pop_item` removes the last item added and returns it."""
    session = SQLiteSession("s1", db_path=tmp_path / "runa.db")

    async def _run():
        await session.add_items([{"role": "user", "content": "first"}])
        await session.add_items([{"role": "user", "content": "second"}])
        popped = await session.pop_item()
        remaining = await session.get_items()
        return popped, remaining

    popped, remaining = asyncio.run(_run())
    assert popped == {"role": "user", "content": "second"}
    assert remaining == [{"role": "user", "content": "first"}]


def test_pop_item_on_empty_session_returns_none(tmp_path: Path) -> None:
    """Popping from a session with no history returns `None`, not an error."""
    session = SQLiteSession("s1", db_path=tmp_path / "runa.db")

    assert asyncio.run(session.pop_item()) is None


def test_clear_session_drops_its_items_and_row(tmp_path: Path) -> None:
    """`clear_session` deletes the session's messages and its `agent_sessions` row."""
    db_path = tmp_path / "runa.db"
    session = SQLiteSession("s1", db_path=db_path)

    async def _run():
        await session.add_items([{"role": "user", "content": "hi"}])
        await session.clear_session()
        return await session.get_items()

    assert asyncio.run(_run()) == []
    with closing(sqlite3.connect(db_path)) as conn:
        row = conn.execute("SELECT 1 FROM agent_sessions WHERE session_id = ?", ("s1",)).fetchone()
    assert row is None


def test_sessions_are_isolated_by_session_id(tmp_path: Path) -> None:
    """Items added under one `session_id` don't leak into another sharing the same `runa.db`."""
    db_path = tmp_path / "runa.db"
    session_a = SQLiteSession("a", db_path=db_path)
    session_b = SQLiteSession("b", db_path=db_path)

    async def _run():
        await session_a.add_items([{"role": "user", "content": "from a"}])
        await session_b.add_items([{"role": "user", "content": "from b"}])
        return await session_a.get_items(), await session_b.get_items()

    items_a, items_b = asyncio.run(_run())
    assert items_a == [{"role": "user", "content": "from a"}]
    assert items_b == [{"role": "user", "content": "from b"}]
