from runa import Runa
from runa import Agent


from tests.fakes import FakeRuntime


def test_agent_runs():
    runa = Runa()
    runa.resolver.register("gpt-5.4-nano", FakeRuntime)

    agent = runa.agent(
        name="assistant",
        instructions="Be helpful.",
        model="gpt-5.4-nano",
    )

    result = agent.run("Hello")

    assert result.output == "Hello from Runa."

def test_agent_can_be_created():
    agent = Agent(
        name="assistant",
        instructions="Be helpful.",
        model="gpt-5.4-nano",
    )

    assert agent.name == "assistant"
    assert agent.model == "gpt-5.4-nano"