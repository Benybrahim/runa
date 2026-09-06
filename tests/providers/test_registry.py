import pytest

from runa.providers import AnthropicProvider, OpenAIProvider
from runa.providers.registry import (
    UnknownModelProvider,
    UnknownProvider,
    resolve_provider,
    resolve_provider_for_model,
)
from tests.fakes import FakeProvider


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


def test_resolve_provider_for_model_infers_openai_from_a_gpt_model_name():
    provider = resolve_provider_for_model("gpt-5.6")

    assert isinstance(provider, OpenAIProvider)


def test_resolve_provider_for_model_infers_openai_from_an_o_series_model_name():
    provider = resolve_provider_for_model("o3-mini")

    assert isinstance(provider, OpenAIProvider)


def test_resolve_provider_for_model_infers_anthropic_from_a_claude_model_name():
    provider = resolve_provider_for_model("claude-sonnet-4")

    assert isinstance(provider, AnthropicProvider)


def test_resolve_provider_for_model_raises_a_clear_error_for_an_unrecognized_model():
    with pytest.raises(UnknownModelProvider, match="unrecognized-model"):
        resolve_provider_for_model("unrecognized-model")


def test_resolve_provider_for_model_does_not_construct_non_matching_providers(
    monkeypatch,
):
    """Inference must rule candidates out by name before constructing them:
    constructing a real Provider needs an API key, which shouldn't be
    required for a provider that was never going to match anyway."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    provider = resolve_provider_for_model("claude-sonnet-4")

    assert isinstance(provider, AnthropicProvider)
