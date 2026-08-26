from runa import Agent
from runa.config import config
from tests.fakes import FakeRuntime


def test_agent_runs():
    config.resolver.register("gpt-5.6", FakeRuntime)

    agent = Agent(
        name="assistant",
        instructions="Be helpful.",
        model="gpt-5.6",
    )

    result = agent.run("Hello")

    assert result.output == "Hello from Runa."