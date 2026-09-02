"""config.py: the app-wide default Provider (manifesto §2, §3).

A model provider is an application-level dependency, not a per-agent one —
most applications talk to exactly one. `configure()` sets it once; `Agent.run()`
and `Agent.run_later()` use it unless an explicit `Executor` is given, which
remains the escape hatch for an agent that genuinely needs a different
provider or strategy (manifesto §9).
"""

from runa.runtime.provider import Provider

_default_provider: Provider | None = None


class ProviderNotConfigured(Exception):
    """Raised when Agent.run()/.run_later() needs a Provider that isn't set."""


def configure(*, provider: Provider) -> None:
    """Set the app-wide default Provider."""
    global _default_provider
    _default_provider = provider


def default_provider() -> Provider:
    if _default_provider is None:
        raise ProviderNotConfigured(
            "call runa.configure(provider=...) before Agent.run(), "
            "or pass an Executor explicitly"
        )
    return _default_provider
