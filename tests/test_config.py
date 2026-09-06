"""runa.config is now a backward-compatible facade over runa.application;
see test_application.py for the Application/Config behavior itself. These
tests only check the facade still wires through correctly.
"""

import pytest

from runa.application import application
from runa.config import (
    ProviderNotConfigured,
    configure,
    default_provider,
    default_run_store,
)
from runa.persistence import InMemoryRunStore
from tests.fakes import FakeProvider


def test_default_provider_raises_before_configure(monkeypatch):
    monkeypatch.setattr(application.config, "provider", None)

    with pytest.raises(ProviderNotConfigured):
        default_provider()


def test_configure_sets_the_default_provider():
    provider = FakeProvider(responses=[])

    configure(provider=provider)

    assert default_provider() is provider
    assert application.config.provider is provider


def test_default_run_store_is_in_memory_until_configured(monkeypatch):
    monkeypatch.setattr(application.config, "run_store", InMemoryRunStore())

    assert isinstance(default_run_store(), InMemoryRunStore)


def test_configure_sets_the_default_run_store():
    provider = FakeProvider(responses=[])
    store = InMemoryRunStore()

    configure(provider=provider, run_store=store)

    assert default_run_store() is store


def test_configure_without_run_store_leaves_the_previous_one(monkeypatch):
    provider = FakeProvider(responses=[])
    store = InMemoryRunStore()
    monkeypatch.setattr(application.config, "run_store", store)

    configure(provider=provider)

    assert default_run_store() is store
