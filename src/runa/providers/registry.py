"""Provider resolution: normalize the `provider="openai"` shorthand into a
concrete Provider instance, or infer one from a bare model name.

Providers are first-class objects everywhere in Runa; the registry exists
only so `Application.configure()` (application.py) can accept the ergonomic
string alias and turn it into one immediately, at the configuration
boundary, and so `Application.provider_for()` can turn an Agent's declared
`model` into one when no provider was configured explicitly. Nothing past
that point ever sees a string; the rest of the framework depends only on
the `Provider` protocol (architecture.md: "Providers never leak inward").
An unrecognized alias raises `UnknownProvider` rather than passing a bare
string through to `Executor`, where it would fail confusingly with an
`AttributeError` on `.complete()`.

Aliases are deliberately static (a plain dict) rather than a dynamic/plugin
loading mechanism: the framework ships a small, known set of providers, and
arbitrary dynamic provider loading is speculative until something actually
needs it. Model inference stays just as static: `resolve_provider_for_model`
asks each known Provider class whether it recognizes the model name (its
`supports()` classmethod) rather than maintaining a second registry keyed
by individual model name, which would need updating on every model release.
"""

from typing import Protocol

from runa.providers.anthropic import AnthropicProvider
from runa.providers.openai import OpenAIProvider
from runa.runtime.provider import Provider


class UnknownProvider(Exception):
    """Raised when a provider alias isn't in the registry."""


class UnknownModelProvider(Exception):
    """Raised when no known Provider recognizes a given model name."""


class _ProviderClass(Protocol):
    """A Provider class registerable here: constructible with no arguments,
    and able to say which model names it recognizes."""

    def __call__(self) -> Provider: ...
    def supports(self, model: str) -> bool: ...


_REGISTRY: dict[str, _ProviderClass] = {
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


def resolve_provider_for_model(model: str) -> Provider:
    """Infer a Provider instance from a bare model name.

    Tries each known Provider class's `supports(model)` classmethod in
    turn and constructs the first one that matches, e.g. `"gpt-5.6"` routes
    to `OpenAIProvider` and `"claude-sonnet-4"` to `AnthropicProvider`. This
    is what lets `Agent(model="gpt-5.6")` work with zero explicit
    `runa.configure(provider=...)` call. Raises `UnknownModelProvider` if no
    known Provider recognizes the model.
    """
    for provider_cls in _REGISTRY.values():
        if provider_cls.supports(model):
            return provider_cls()
    known = ", ".join(sorted(_REGISTRY))
    raise UnknownModelProvider(
        f"no provider recognizes model {model!r}; known providers: {known}. "
        "Configure one explicitly with runa.configure(provider=...)."
    )
