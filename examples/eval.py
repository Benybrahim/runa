"""eval.py: check agent behavior with the eval harness.

`run_evals()` drives the same Agent/Executor/Run path as production, not a
separate mocked harness. The first two cases are invariants: deterministic
checks against the resulting Run, the same way an application test would
read it. The third is a behavioral evaluation: `to_be_helpful()` sends the
Run's transcript to a Judge and grades it, which costs a real model call and
isn't deterministic; that's the line manifesto §12 draws between tests and
evals.

Requires OPENAI_API_KEY in the environment.
Run with: uv run python examples/eval.py
"""

from runa import (
    Agent,
    EvalCase,
    Executor,
    Judge,
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


provider = OpenAIProvider()
judge = Judge(provider)  # reuses the same Provider, no separate judge client

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
    EvalCase(
        name="is a helpful answer, not just a completed run",
        input="What's the weather in Osaka?",
        check=lambda run: expect(run).to_be_completed().to_be_helpful(judge=judge),
    ),
]


if __name__ == "__main__":
    executor = Executor(provider=provider)
    agent = WeatherAgent()

    for result in run_evals(agent, executor, cases):
        status = "PASS" if result.passed else f"FAIL: {result.error}"
        print(f"{result.case.name}: {status}")
