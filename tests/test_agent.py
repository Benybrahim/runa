from runa import Agent

from tests.fakes import FakeRuntime


def test_agent_runs():
    agent = Agent(
        name="assistant",
        instructions="Be helpful.",
        model="gpt-5.6",
        runtime=FakeRuntime(),
    )

    result = agent.run("Hello")

    assert result.output == "Hello from Runa."