"""background.py: queue a run for background execution.

`run_later()` produces the same kind of Run as `run()`; with the default
InlineQueue it runs synchronously and returns a completed Run immediately.
A real Queue (backed by a task queue, a worker process) defers the work
elsewhere without this code changing at all.

Requires OPENAI_API_KEY in the environment.
Run with: uv run python examples/background.py
"""

from runa import Agent, tool


@tool
def get_weather(city: str) -> str:
    return f"{city}: sunny, 22C"


class WeatherAgent(Agent):
    model = "gpt-5-nano"
    instructions = "Answer weather questions using the get_weather tool."
    tools = [get_weather]


if __name__ == "__main__":
    run = WeatherAgent.run_later("What's the weather in Kyoto?")
    print(run.status, run.result)
