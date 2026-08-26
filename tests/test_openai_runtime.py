from runa.providers.openai import OpenAIRuntime


def test_openai_runtime_exists():
    runtime = OpenAIRuntime()

    assert runtime is not None