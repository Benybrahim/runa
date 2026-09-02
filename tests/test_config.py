import pytest

from runa.config import ProviderNotConfigured, configure, default_provider
from tests.fakes import FakeProvider


def test_default_provider_raises_before_configure(monkeypatch):
    monkeypatch.setattr("runa.config._default_provider", None)

    with pytest.raises(ProviderNotConfigured):
        default_provider()


def test_configure_sets_the_default_provider():
    provider = FakeProvider(responses=[])

    configure(provider=provider)

    assert default_provider() is provider
