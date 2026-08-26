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


def test_agent_accepts_tools():
    def get_weather(city: str) -> str:
        return f"Sunny in {city}"

    agent = Agent(
        name="assistant",
        instructions="Be helpful.",
        model="gpt-5.4-nano",
        tools=[get_weather],
    )

    assert agent.tools == [get_weather]

def test_run_has_an_id():
    runa = Runa()
    runa.resolver.register("gpt-5.4-nano", FakeRuntime)

    agent = runa.agent(
        name="assistant",
        instructions="Be helpful.",
        model="gpt-5.4-nano",
    )

    result = agent.run("Hello")

    assert result.id
    assert result.output == "Hello from Runa."
    assert result.id != agent.run("Hello").id
