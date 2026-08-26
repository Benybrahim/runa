from runa import Agent
from runa.resolver import ModelResolver

from tests.fakes import FakeRuntime


def test_agent_runs():
    resolver = ModelResolver()
    resolver.register("gpt-5.4-nano", FakeRuntime)

    agent = Agent(
        name="assistant",
        instructions="Be helpful.",
        model="gpt-5.4-nano",
        _resolver=resolver,
    )

    result = agent.run("Hello")

    assert result.output == "Hello from Runa."