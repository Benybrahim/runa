from runa.config import config
from runa.providers.openai import OpenAIRuntime


def test_gpt_model_uses_openai_runtime():
    runtime = config.resolver.resolve("gpt-5.4-nano")

    assert isinstance(runtime, OpenAIRuntime)

def test_any_gpt_model_uses_openai_runtime():
    runtime = config.resolver.resolve("gpt-5.6")

    assert isinstance(runtime, OpenAIRuntime)