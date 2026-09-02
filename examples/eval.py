"""eval.py: check agent behavior with the eval harness.

`run_evals()` drives the same Agent/Executor/Run path as production, not a
separate mocked harness — `expect(run).to_...()` reads the resulting Run
the same way an application invariant would.

Requires OPENAI_API_KEY in the environment.
Run with: uv run python examples/eval.py
"""

from runa import (
    Agent,
    EvalCase,
    Executor,
    OpenAIProvider,
    expect,
    run_evals,
    tool,
)


@tool
def get_weather(city: str) -> str:
    return f"{city}: sunny, 22C"


class WeatherAgent(Agent):
    instructions = "Answer weather questions using the get_weather tool."
    tools = [get_weather]


cases = [
    EvalCase(
        name="calls the weather tool",
        input="What's the weather in Tokyo?",
        check=lambda run: expect(run).to_be_completed().to_have_called("get_weather"),
    ),
    EvalCase(
        name="mentions the city in its answer",
        input="What's the weather in Kyoto?",
        check=lambda run: expect(run).to_be_completed().to_contain("Kyoto"),
    ),
]


if __name__ == "__main__":
    executor = Executor(provider=OpenAIProvider())
    agent = WeatherAgent()

    for result in run_evals(agent, executor, cases):
        status = "PASS" if result.passed else f"FAIL: {result.error}"
        print(f"{result.case.name}: {status}")
