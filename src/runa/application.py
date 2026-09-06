"""Application: the app-wide configuration boundary (RUNA.md §2, §5).

A Runa application shares one set of runtime infrastructure (model
provider, run persistence, and, later, execution, telemetry, logging,
hooks, serialization) across every Agent it runs. `Application` is the
object that owns that infrastructure; `Config` is the plain data it holds.
Structuring it as a dataclass rather than separate globals means new shared
infrastructure is a new `Config` field, not a new module-level variable
threaded through every call site that needs it.

`application` (module-level, below) is the default `Application`, created
once at import time. `runa.configure(**options)` is convenience sugar for
`application.configure(**options)`; most applications talk to exactly one
Application and never construct their own. `Agent.run()` and friends
(agent.py) resolve their provider from this default instance so a provider
is not threaded through every call.

Construct `Application()` explicitly for tests, or any scenario that needs
an isolated set of infrastructure: each instance owns its own `Config`, so
configuring one instance never leaks into another (see
tests/test_application.py). Its async_provider/provider/run_store can be
passed straight into an `Executor`, the same escape hatch
`Agent.run(executor=...)` already exposes, so an isolated Application
doesn't need any Agent-level API of its own to be useful.

A model provider is an application-level dependency, not a per-agent one:
most applications talk to exactly one. `async_provider` drives `Executor`
(Runa's canonical execution model, see `runtime/executor.py`); `provider`
is a separate, synchronous slot for direct use outside an Agent's own
Executor, e.g. the default `Judge` in `eval/harness.py`. A sync client
(`anthropic.Anthropic`) and an async one (`anthropic.AsyncAnthropic`) are
different objects, so an app that wants both configures them explicitly.

`run_store` defaults to an in-memory store, so it's only useful across
process boundaries once an app configures a durable one, e.g.
`configure(provider=..., run_store=SQLiteRunStore(...))`.
"""

from dataclasses import dataclass, field, fields

from runa.persistence.store import InMemoryRunStore, RunStore
from runa.providers.registry import resolve_async_provider, resolve_provider
from runa.runtime.async_provider import AsyncProvider
from runa.runtime.provider import Provider


class ProviderNotConfigured(Exception):
    """Raised when the default synchronous Provider is needed but isn't set,
    e.g. by `Judge`'s default in `eval/harness.py`."""


class AsyncProviderNotConfigured(Exception):
    """Raised when Agent.run()/.run_sync()/.run_stream()/.run_later() needs
    an AsyncProvider that isn't set."""


class InvalidConfiguration(Exception):
    """Raised when Application.configure() is given an unrecognized option."""


@dataclass
class Config:
    """Application-wide shared infrastructure.

    New shared infrastructure (persistence, execution, telemetry, logging,
    hooks, serialization, ...) gets a new field here. `Application.configure()`
    validates its keyword options against these field names directly, so a
    new field is automatically a new valid `configure()` option with no
    further wiring.
    """

    provider: Provider | None = None
    async_provider: AsyncProvider | None = None
    run_store: RunStore = field(default_factory=InMemoryRunStore)


class Application:
    """Owns one application's shared runtime configuration.

    Configure it once at startup:

        app = runa.Application()
        app.configure(provider=OpenAIProvider())

    or, for the common single-application case, configure the default
    instance through the module-level convenience function:

        runa.configure(provider=OpenAIProvider())

    which delegates to `runa.application.configure(...)`. `provider` also
    accepts the ergonomic string alias for the common case with no
    provider-specific configuration:

        runa.configure(provider="openai")
    """

    def __init__(self) -> None:
        self.config = Config()

    def configure(self, **options: object) -> None:
        """Set one or more `Config` fields explicitly.

        Only the options passed are touched: anything already configured
        and left out of this call keeps its current value (so
        `configure(provider=...)` alone never resets an already-configured
        `run_store`). Raises `InvalidConfiguration` for a keyword that
        isn't a known `Config` field, so a typo like `provder=...` fails
        loudly instead of being silently ignored.

        `provider`/`async_provider` accept either a `Provider`/`AsyncProvider`
        instance or its ergonomic string alias (`provider="openai"`); the
        alias is resolved to an instance right here, so `self.config` and
        everything downstream only ever sees a real Provider (see
        `runa.providers.registry.resolve_provider`). An unrecognized alias
        raises `UnknownProvider` immediately, at configure() time, rather
        than failing later inside the runtime.
        """
        valid_fields = {f.name for f in fields(Config)}
        unknown = set(options) - valid_fields
        if unknown:
            raise InvalidConfiguration(
                f"unknown configuration option(s): {', '.join(sorted(unknown))}; "
                f"valid options are: {', '.join(sorted(valid_fields))}"
            )
        resolvers = {
            "provider": resolve_provider,
            "async_provider": resolve_async_provider,
        }
        for name, value in options.items():
            resolve = resolvers.get(name)
            if resolve is not None and value is not None:
                value = resolve(value)
            setattr(self.config, name, value)

    @property
    def provider(self) -> Provider:
        if self.config.provider is None:
            raise ProviderNotConfigured(
                "call runa.configure(provider=...) first, or pass a Provider "
                "explicitly, e.g. Judge(my_provider)"
            )
        return self.config.provider

    @property
    def async_provider(self) -> AsyncProvider:
        if self.config.async_provider is None:
            raise AsyncProviderNotConfigured(
                "call runa.configure(async_provider=...) before Agent.run()/"
                ".run_sync()/.run_stream()/.run_later(), or pass an "
                "Executor explicitly"
            )
        return self.config.async_provider

    @property
    def run_store(self) -> RunStore:
        return self.config.run_store


application = Application()


def configure(**options: object) -> None:
    """Configure the default Application. See `Application.configure()`."""
    application.configure(**options)
