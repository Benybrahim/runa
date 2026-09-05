import pytest

from runa.providers import AnthropicProvider, AsyncOpenAIProvider, OpenAIProvider
from runa.providers.registry import (
    UnknownProvider,
    resolve_async_provider,
    resolve_provider,
)
from tests.fakes import FakeAsyncProvider, FakeProvider


@pytest.fixture(autouse=True)
def _fake_api_keys(monkeypatch):
    """Constructing a real provider only needs *a* key present, not a valid
    one: no network call happens until `.complete()`."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")


def test_resolve_provider_passes_an_existing_instance_through_unchanged():
    provider = FakeProvider(responses=[])

    assert resolve_provider(provider) is provider


def test_resolve_provider_resolves_the_openai_alias():
    provider = resolve_provider("openai")

    assert isinstance(provider, OpenAIProvider)


def test_resolve_provider_resolves_the_anthropic_alias():
    provider = resolve_provider("anthropic")

    assert isinstance(provider, AnthropicProvider)


def test_resolve_provider_raises_a_clear_error_for_an_unknown_alias():
    with pytest.raises(UnknownProvider, match="unrecognized-vendor"):
        resolve_provider("unrecognized-vendor")


def test_resolve_async_provider_passes_an_existing_instance_through_unchanged():
    provider = FakeAsyncProvider(responses=[])

    assert resolve_async_provider(provider) is provider


def test_resolve_async_provider_resolves_the_openai_alias():
    provider = resolve_async_provider("openai")

    assert isinstance(provider, AsyncOpenAIProvider)


def test_resolve_async_provider_raises_a_clear_error_for_an_unknown_alias():
    with pytest.raises(UnknownProvider, match="unrecognized-vendor"):
        resolve_async_provider("unrecognized-vendor")
