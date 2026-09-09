"""Tests for `runa.cache.MemoryCache` and `runa.cache.SQLiteCache`."""

import asyncio
from pathlib import Path

import pytest

from runa.cache import Cache, MemoryCache, SQLiteCache


def _caches(tmp_path: Path) -> list[Cache]:
    return [MemoryCache(), SQLiteCache(tmp_path / "runa.db")]


@pytest.mark.parametrize("cache_index", [0, 1])
def test_get_on_missing_key_returns_none(tmp_path: Path, cache_index: int) -> None:
    """A key that was never set is a miss, not an error."""
    cache = _caches(tmp_path)[cache_index]

    assert asyncio.run(cache.get("missing")) is None


@pytest.mark.parametrize("cache_index", [0, 1])
def test_set_then_get_round_trips_the_value(tmp_path: Path, cache_index: int) -> None:
    """A value set without a `ttl` comes back unchanged and never expires."""
    cache = _caches(tmp_path)[cache_index]

    async def _run():
        await cache.set("key", {"a": 1, "b": [1, 2, 3]})
        return await cache.get("key")

    assert asyncio.run(_run()) == {"a": 1, "b": [1, 2, 3]}


@pytest.mark.parametrize("cache_index", [0, 1])
def test_set_overwrites_an_existing_value(tmp_path: Path, cache_index: int) -> None:
    """Setting an already-used key replaces its value rather than erroring or appending."""
    cache = _caches(tmp_path)[cache_index]

    async def _run():
        await cache.set("key", "first")
        await cache.set("key", "second")
        return await cache.get("key")

    assert asyncio.run(_run()) == "second"


@pytest.mark.parametrize("cache_index", [0, 1])
def test_delete_removes_the_key(tmp_path: Path, cache_index: int) -> None:
    """A deleted key is a miss afterward."""
    cache = _caches(tmp_path)[cache_index]

    async def _run():
        await cache.set("key", "value")
        await cache.delete("key")
        return await cache.get("key")

    assert asyncio.run(_run()) is None


@pytest.mark.parametrize("cache_index", [0, 1])
def test_delete_on_missing_key_does_not_raise(tmp_path: Path, cache_index: int) -> None:
    """Deleting a key that was never set is a no-op, not an error."""
    cache = _caches(tmp_path)[cache_index]

    asyncio.run(cache.delete("missing"))


@pytest.mark.parametrize("cache_index", [0, 1])
def test_clear_removes_every_entry(tmp_path: Path, cache_index: int) -> None:
    """`clear` empties the whole cache, not just one key."""
    cache = _caches(tmp_path)[cache_index]

    async def _run():
        await cache.set("a", 1)
        await cache.set("b", 2)
        await cache.clear()
        return await cache.get("a"), await cache.get("b")

    assert asyncio.run(_run()) == (None, None)


@pytest.mark.parametrize("cache_index", [0, 1])
def test_expired_entry_behaves_as_a_miss(tmp_path: Path, cache_index: int) -> None:
    """A key set with a `ttl` in the past is already expired the moment it's read."""
    cache = _caches(tmp_path)[cache_index]

    async def _run():
        await cache.set("key", "value", ttl=-1)
        return await cache.get("key")

    assert asyncio.run(_run()) is None


@pytest.mark.parametrize("cache_index", [0, 1])
def test_unexpired_entry_is_still_a_hit(tmp_path: Path, cache_index: int) -> None:
    """A key set with a `ttl` far in the future is still readable."""
    cache = _caches(tmp_path)[cache_index]

    async def _run():
        await cache.set("key", "value", ttl=3600)
        return await cache.get("key")

    assert asyncio.run(_run()) == "value"


def test_sqlite_cache_persists_across_instances(tmp_path: Path) -> None:
    """A value survives past the `SQLiteCache` instance that wrote it, unlike `MemoryCache`."""
    db_path = tmp_path / "runa.db"

    async def _run():
        await SQLiteCache(db_path).set("key", "value")
        return await SQLiteCache(db_path).get("key")

    assert asyncio.run(_run()) == "value"


def test_memory_cache_does_not_persist_across_instances(tmp_path: Path) -> None:
    """A fresh `MemoryCache` starts empty, even for a key another instance set."""

    async def _run():
        await MemoryCache().set("key", "value")
        return await MemoryCache().get("key")

    assert asyncio.run(_run()) is None
