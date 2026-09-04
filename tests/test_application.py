import pytest

import runa
from runa.agent import Agent
from runa.application import (
    Application,
    AsyncProviderNotConfigured,
    Config,
    InvalidConfiguration,
    ProviderNotConfigured,
    application,
)
from runa.core import Message, Role, RunStatus
from runa.persistence import InMemoryRunStore
from runa.providers import AsyncOpenAIProvider, OpenAIProvider, UnknownProvider
from tests.fakes import FakeAsyncProvider, FakeProvider


@pytest.fixture(autouse=True)
def _reset_default_application(monkeypatch):
    """Every test gets the default Application back to a fresh Config."""
    monkeypatch.setattr(application, "config", Config())


def test_runa_application_is_the_default_application():
    assert isinstance(runa.application, Application)
    assert runa.application is application


def test_runa_configure_sets_the_default_applications_provider():
    provider = FakeProvider(responses=[])

    runa.configure(provider=provider)

    assert runa.application.provider is provider


def test_application_provider_raises_before_configuration():
    with pytest.raises(ProviderNotConfigured):
        application.provider


def test_application_async_provider_raises_before_configuration():
    with pytest.raises(AsyncProviderNotConfigured):
        application.async_provider


def test_application_run_store_defaults_to_in_memory():
    assert isinstance(application.run_store, InMemoryRunStore)


def test_configure_only_touches_the_options_passed():
    store = InMemoryRunStore()
    application.configure(run_store=store)
    provider = FakeProvider(responses=[])

    application.configure(provider=provider)

    assert application.provider is provider
    assert application.run_store is store  # untouched by the second call


def test_configure_rejects_an_unknown_option():
    with pytest.raises(InvalidConfiguration):
        application.configure(model_provider=FakeProvider(responses=[]))


def test_configure_resolves_a_string_provider_alias(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    application.configure(provider="openai")

    assert isinstance(application.provider, OpenAIProvider)


def test_configure_still_accepts_an_explicit_provider_instance():
    provider = FakeProvider(responses=[])

    application.configure(provider=provider)

    assert application.provider is provider


def test_configure_raises_a_clear_error_for_an_unknown_provider_alias():
    with pytest.raises(UnknownProvider, match="unrecognized-vendor"):
        application.configure(provider="unrecognized-vendor")


def test_configure_resolves_a_string_async_provider_alias(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    application.configure(provider=FakeProvider(responses=[]), async_provider="openai")

    assert isinstance(application.async_provider, AsyncOpenAIProvider)


def test_explicit_application_can_be_constructed_and_configured():
    app = Application()
    provider = FakeProvider(responses=[])

    app.configure(provider=provider)

    assert app.provider is provider


def test_independently_created_applications_are_isolated():
    app_a = Application()
    app_b = Application()
    provider_a = FakeProvider(responses=[])
    provider_b = FakeProvider(responses=[])

    app_a.configure(provider=provider_a)
    app_b.configure(provider=provider_b)

    assert app_a.provider is provider_a
    assert app_b.provider is provider_b
    assert app_a.provider is not app_b.provider


def test_configuring_an_explicit_application_does_not_affect_the_default():
    app = Application()
    app.configure(provider=FakeProvider(responses=[]))

    with pytest.raises(ProviderNotConfigured):
        application.provider


def test_agent_run_resolves_the_provider_from_the_default_application():
    class SimpleAgent(Agent):
        pass

    runa.configure(provider=FakeProvider([Message(role=Role.ASSISTANT, content="hi")]))

    run = SimpleAgent.run("hello")

    assert run.status == RunStatus.COMPLETED
    assert run.result == "hi"


def test_agent_run_async_resolves_the_async_provider_from_the_default_application():
    import asyncio

    class SimpleAgent(Agent):
        pass

    runa.configure(
        provider=FakeProvider([]),
        async_provider=FakeAsyncProvider([Message(role=Role.ASSISTANT, content="hi")]),
    )

    run = asyncio.run(SimpleAgent.run_async("hello"))

    assert run.status == RunStatus.COMPLETED
    assert run.result == "hi"


def test_agent_run_raises_a_clear_error_when_no_provider_is_configured():
    class SimpleAgent(Agent):
        pass

    with pytest.raises(ProviderNotConfigured):
        SimpleAgent.run("hello")


def test_agent_run_still_accepts_an_explicit_executor_without_any_configuration():
    from runa.runtime import Executor

    class SimpleAgent(Agent):
        pass

    provider = FakeProvider([Message(role=Role.ASSISTANT, content="hi")])

    run = SimpleAgent.run("hello", executor=Executor(provider=provider))

    assert run.status == RunStatus.COMPLETED
    assert run.result == "hi"
