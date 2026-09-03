import pytest

from runa.config import (
    ProviderNotConfigured,
    configure,
    default_provider,
    default_run_store,
)
from runa.persistence import InMemoryRunStore
from tests.fakes import FakeProvider


def test_default_provider_raises_before_configure(monkeypatch):
    monkeypatch.setattr("runa.config._default_provider", None)

    with pytest.raises(ProviderNotConfigured):
        default_provider()


def test_configure_sets_the_default_provider():
    provider = FakeProvider(responses=[])

    configure(provider=provider)

    assert default_provider() is provider


def test_default_run_store_is_in_memory_until_configured(monkeypatch):
    monkeypatch.setattr("runa.config._default_run_store", InMemoryRunStore())

    assert isinstance(default_run_store(), InMemoryRunStore)


def test_configure_sets_the_default_run_store():
    provider = FakeProvider(responses=[])
    store = InMemoryRunStore()

    configure(provider=provider, run_store=store)

    assert default_run_store() is store


def test_configure_without_run_store_leaves_the_previous_one(monkeypatch):
    provider = FakeProvider(responses=[])
    store = InMemoryRunStore()
    monkeypatch.setattr("runa.config._default_run_store", store)

    configure(provider=provider)

    assert default_run_store() is store
