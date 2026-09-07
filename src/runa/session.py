"""Sessions with `.compact()` sugar for OpenAI responses compaction."""

from typing import Any

from agents import OpenAIResponsesCompactionSession
from agents.extensions.memory.async_sqlite_session import AsyncSQLiteSession as _AsyncSQLiteSession
from agents.extensions.memory.redis_session import RedisSession as _RedisSession
from agents.memory.session import SessionABC
from agents.memory.sqlite_session import SQLiteSession as _SQLiteSession


class _Compactable(SessionABC):
    """Mixin adding `.compact()` to a session that tracks its own `session_id`."""

    def compact(self, **kwargs: Any) -> OpenAIResponsesCompactionSession:
        """Wrap this session in an `OpenAIResponsesCompactionSession` over itself.

        `session_id` is taken from this session, so it never needs repeating. Extra keyword
        arguments (`client`, `model`, `compaction_mode`, `should_trigger_compaction`) are
        forwarded to `OpenAIResponsesCompactionSession` as-is.
        """
        return OpenAIResponsesCompactionSession(
            session_id=self.session_id, underlying_session=self, **kwargs
        )


class SQLiteSession(_Compactable, _SQLiteSession):
    """`SQLiteSession` with `.compact()` sugar."""


class AsyncSQLiteSession(_Compactable, _AsyncSQLiteSession):
    """`AsyncSQLiteSession` with `.compact()` sugar."""


class RedisSession(_Compactable, _RedisSession):
    """`RedisSession` with `.compact()` sugar."""


__all__ = ["AsyncSQLiteSession", "RedisSession", "SQLiteSession"]
