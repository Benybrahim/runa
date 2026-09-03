"""config.py: the app-wide default Provider and RunStore (manifesto §2, §3).

A model provider is an application-level dependency, not a per-agent one —
most applications talk to exactly one. `configure()` sets it once; `Agent.run()`
and `Agent.run_later()` use it unless an explicit `Executor` is given, which
remains the escape hatch for an agent that genuinely needs a different
provider or strategy (manifesto §9).

`async_provider` is a separate, independent slot rather than something
derived from `provider`: a sync client (`anthropic.Anthropic`) and an async
one (`anthropic.AsyncAnthropic`) are different objects, so an app that wants
`Agent.run_async()` to work configures both explicitly.

The default `RunStore` is the same kind of app-wide dependency: `runa runs
show <id>` (cli/runs.py) has nowhere else to look a Run up. It defaults to an
in-memory store, so it's only useful across process boundaries once an app
configures a durable one, e.g. `configure(provider=..., run_store=
SQLiteRunStore(...))`.
"""

from runa.persistence.store import InMemoryRunStore, RunStore
from runa.runtime.async_provider import AsyncProvider
from runa.runtime.provider import Provider

_default_provider: Provider | None = None
_default_async_provider: AsyncProvider | None = None
_default_run_store: RunStore = InMemoryRunStore()


class ProviderNotConfigured(Exception):
    """Raised when Agent.run()/.run_later() needs a Provider that isn't set."""


class AsyncProviderNotConfigured(Exception):
    """Raised when Agent.run_async() needs an AsyncProvider that isn't set."""


def configure(
    *,
    provider: Provider,
    async_provider: AsyncProvider | None = None,
    run_store: RunStore | None = None,
) -> None:
    """Set the app-wide default Provider, and optionally AsyncProvider/RunStore."""
    global _default_provider, _default_async_provider, _default_run_store
    _default_provider = provider
    if async_provider is not None:
        _default_async_provider = async_provider
    if run_store is not None:
        _default_run_store = run_store


def default_provider() -> Provider:
    if _default_provider is None:
        raise ProviderNotConfigured(
            "call runa.configure(provider=...) before Agent.run(), "
            "or pass an Executor explicitly"
        )
    return _default_provider


def default_async_provider() -> AsyncProvider:
    if _default_async_provider is None:
        raise AsyncProviderNotConfigured(
            "call runa.configure(provider=..., async_provider=...) before "
            "Agent.run_async(), or pass an AsyncExecutor explicitly"
        )
    return _default_async_provider


def default_run_store() -> RunStore:
    return _default_run_store
