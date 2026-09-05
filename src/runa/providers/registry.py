"""Provider resolution: normalize the `provider="openai"` shorthand into a
concrete Provider instance.

Providers are first-class objects everywhere in Runa; the registry exists
only so `Application.configure()` (application.py) can accept the ergonomic
string alias and turn it into one immediately, at the configuration
boundary. Nothing past that point ever sees a string; the rest of the
framework depends only on the `Provider`/`AsyncProvider` protocols
(architecture.md: "Providers never leak inward"). An unrecognized alias
raises `UnknownProvider` rather than passing a bare string through to
`Executor`, where it would fail confusingly with an `AttributeError` on
`.complete()`.

Aliases are deliberately static (a plain dict) rather than a dynamic/plugin
loading mechanism: the framework ships a small, known set of providers, and
arbitrary dynamic provider loading is speculative until something actually
needs it.
"""

from runa.providers.anthropic import AnthropicProvider, AsyncAnthropicProvider
from runa.providers.openai import AsyncOpenAIProvider, OpenAIProvider
from runa.runtime.async_provider import AsyncProvider
from runa.runtime.provider import Provider


class UnknownProvider(Exception):
    """Raised when a provider alias isn't in the registry."""


_REGISTRY: dict[str, tuple[type[Provider], type[AsyncProvider]]] = {
    "openai": (OpenAIProvider, AsyncOpenAIProvider),
    "anthropic": (AnthropicProvider, AsyncAnthropicProvider),
}


def _lookup(name: str) -> tuple[type[Provider], type[AsyncProvider]]:
    try:
        return _REGISTRY[name]
    except KeyError:
        known = ", ".join(sorted(_REGISTRY))
        raise UnknownProvider(
            f"unknown provider {name!r}; known providers: {known}"
        ) from None


def resolve_provider(provider: Provider | str) -> Provider:
    """Normalize `provider=` into a `Provider` instance.

    A string looks itself up in the registry and is constructed with no
    arguments: the shorthand covers the common case only; configuration
    like `api_key=`/`base_url=` requires passing an instance directly
    (`OpenAIProvider(base_url=...)`). A `Provider` instance passes through
    unchanged.
    """
    if isinstance(provider, str):
        sync, _ = _lookup(provider)
        return sync()
    return provider


def resolve_async_provider(async_provider: AsyncProvider | str) -> AsyncProvider:
    """The `async_provider=` counterpart to `resolve_provider()`."""
    if isinstance(async_provider, str):
        _, async_cls = _lookup(async_provider)
        return async_cls()
    return async_provider
