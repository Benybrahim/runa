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
tests/test_application.py). Its provider/run_store can be passed straight
into an `Executor`, the same escape hatch `Agent.run(executor=...)` already
exposes, so an isolated Application doesn't need any Agent-level API of its
own to be useful.

A model provider is an application-level dependency, not a per-agent one:
most applications talk to exactly one. `provider` drives both `Executor`
(Runa's canonical execution model, see `runtime/executor.py`) and direct
use outside an Agent's own Executor, e.g. the default `Judge` in
`eval/harness.py`: one Provider, one async contract, no separate
synchronous slot to keep in sync with it.

`run_store` defaults to an in-memory store, so it's only useful across
process boundaries once an app configures a durable one, e.g.
`configure(provider=..., run_store=SQLiteRunStore(...))`.
"""

from dataclasses import dataclass, field, fields
from typing import cast

from runa.persistence.store import InMemoryRunStore, RunStore
from runa.providers.registry import (
    UnknownModelProvider,
    resolve_provider,
    resolve_provider_for_model,
)
from runa.runtime.provider import Provider


class ProviderNotConfigured(Exception):
    """Raised when Agent.run()/.run_sync()/.run_stream()/.run_later() or a
    direct use like `Judge`'s default needs a Provider that isn't set."""


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

        `provider` accepts either a `Provider` instance or its ergonomic
        string alias (`provider="openai"`); the alias is resolved to an
        instance right here, so `self.config` and everything downstream
        only ever sees a real Provider (see
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
        for name, value in options.items():
            if name == "provider" and value is not None:
                value = resolve_provider(cast(Provider | str, value))
            setattr(self.config, name, value)

    @property
    def provider(self) -> Provider:
        if self.config.provider is None:
            raise ProviderNotConfigured(
                "call runa.configure(provider=...) before Agent.run()/"
                ".run_sync()/.run_stream()/.run_later(), or pass an "
                "Executor explicitly, e.g. Judge(my_provider)"
            )
        return self.config.provider

    def provider_for(self, model: str | None) -> Provider:
        """Resolve the Provider an Agent call should use, given its declared
        `model` (`Agent.model`, possibly `None`).

        An explicitly configured provider (`configure(provider=...)`)
        always wins, matching `.provider` above. Only when none is
        configured does `model` get consulted: it's inferred to a Provider
        via `providers.registry.resolve_provider_for_model` (e.g.
        `"gpt-5.6"` -> `OpenAIProvider`), which is what lets
        `Agent(model="gpt-5.6")` run with no `configure()` call at all.
        Raises `ProviderNotConfigured` if neither resolves.
        """
        if self.config.provider is not None:
            return self.config.provider
        if model is not None:
            try:
                return resolve_provider_for_model(model)
            except UnknownModelProvider as exc:
                raise ProviderNotConfigured(str(exc)) from exc
        raise ProviderNotConfigured(
            "call runa.configure(provider=...) before Agent.run()/"
            ".run_sync()/.run_stream()/.run_later(), set Agent.model to a "
            'recognized model name (e.g. "gpt-5.6", "claude-sonnet-4"), '
            "or pass an Executor explicitly, e.g. Judge(my_provider)"
        )

    @property
    def run_store(self) -> RunStore:
        return self.config.run_store


application = Application()


def configure(**options: object) -> None:
    """Configure the default Application. See `Application.configure()`."""
    application.configure(**options)
