"""Provider resolution: normalize the `provider="openai"` shorthand into a
concrete Provider instance.

Providers are first-class objects everywhere in Runa; the registry exists
only so `Application.configure()` (application.py) can accept the ergonomic
string alias and turn it into one immediately, at the configuration
boundary. Nothing past that point ever sees a string; the rest of the
framework depends only on the `Provider` protocol (architecture.md:
"Providers never leak inward"). An unrecognized alias raises
`UnknownProvider` rather than passing a bare string through to `Executor`,
where it would fail confusingly with an `AttributeError` on `.complete()`.

Aliases are deliberately static (a plain dict) rather than a dynamic/plugin
loading mechanism: the framework ships a small, known set of providers, and
arbitrary dynamic provider loading is speculative until something actually
needs it.
"""

from runa.providers.anthropic import AnthropicProvider
from runa.providers.openai import OpenAIProvider
from runa.runtime.provider import Provider


class UnknownProvider(Exception):
    """Raised when a provider alias isn't in the registry."""


_REGISTRY: dict[str, type[Provider]] = {
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
}


def resolve_provider(provider: Provider | str) -> Provider:
    """Normalize `provider=` into a `Provider` instance.

    A string looks itself up in the registry and is constructed with no
    arguments: the shorthand covers the common case only; configuration
    like `api_key=`/`base_url=` requires passing an instance directly
    (`OpenAIProvider(base_url=...)`). A `Provider` instance passes through
    unchanged.
    """
    if isinstance(provider, str):
        try:
            provider_cls = _REGISTRY[provider]
        except KeyError:
            known = ", ".join(sorted(_REGISTRY))
            raise UnknownProvider(
                f"unknown provider {provider!r}; known providers: {known}"
            ) from None
        return provider_cls()
    return provider
