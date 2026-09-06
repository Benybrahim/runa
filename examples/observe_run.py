"""observe_run.py: print a Run's timeline, in-process and live.

`timeline(run)` reads a human-readable view straight off `run.events`, no
setup, no separate tracing system. `instrument(run, subscriber)` does the
same thing live, calling `subscriber` with each `Event` as the Run emits
it, so you can print progress as execution happens rather than after.

Requires OPENAI_API_KEY in the environment.
Run with: uv run python examples/observe_run.py
"""

import asyncio

from runa import (
    Agent,
    Executor,
    OpenAIProvider,
    Run,
    configure,
    tool,
)
from runa.observability import instrument, timeline


@tool
def get_weather(city: str) -> str:
    return f"{city}: sunny, 22C"


class WeatherAgent(Agent):
    instructions = "Answer weather questions using the get_weather tool."
    tools = [get_weather]


if __name__ == "__main__":
    configure(provider=OpenAIProvider())

    print("--- live, as events happen ---")
    run = Run(input="What's the weather in Tokyo?")
    instrument(run, lambda event: print(f"  {event.type.value}"))
    asyncio.run(Executor(OpenAIProvider()).run(WeatherAgent(), run))

    print("\n--- after the fact, from the recorded timeline ---")
    for entry in timeline(run):
        print(f"  {entry.timestamp:%H:%M:%S} {entry.summary}")
