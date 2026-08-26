import pytest

from runa.resolver import ModelResolver
from tests.fakes import FakeRuntime


def test_resolves_registered_model():
    resolver = ModelResolver()
    resolver.register("gpt-5.6", FakeRuntime)

    runtime = resolver.resolve("gpt-5.6")

    assert isinstance(runtime, FakeRuntime)


def test_rejects_unknown_model():
    resolver = ModelResolver()

    with pytest.raises(ValueError, match="Unsupported model: unknown"):
        resolver.resolve("unknown")