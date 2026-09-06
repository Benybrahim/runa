"""parallel_delegate.py: two sub-agents delegated to concurrently (manifesto §6).

Every delegation's `DelegateAgent.call()` is `async def` and awaits its
Executor directly, so when a model turn requests both sub-agents at once,
Executor's existing concurrent tool-call batching (see Executor's
docstring) runs them as genuine concurrent async I/O rather than one
network call at a time. No special wiring needed: a bare class in
`delegations` (e.g. `delegations = [WeatherAgent]`) already gets this,
`DelegateAgent(WeatherAgent)` only exists as the escape hatch for
overriding a delegation's `executor` explicitly.

A Return delegate (both of these are) runs its own nested Run, with its own
Provider resolved from its own `model`, independently of the delegating
Agent's: all three classes here declare one.

Requires OPENAI_API_KEY in the environment.
Run with: uv run python examples/parallel_delegate.py
"""

import asyncio

from runa import Agent


class WeatherAgent(Agent):
    model = "gpt-5-nano"
    instructions = "Answer weather questions concisely."


class NewsAgent(Agent):
    model = "gpt-5-nano"
    instructions = "Summarize one plausible top headline for a city, concisely."


class BriefingAgent(Agent):
    model = "gpt-5-nano"
    instructions = (
        "Given a city, call both WeatherAgent and NewsAgent, then combine "
        "their answers into a short morning briefing."
    )
    delegations = [WeatherAgent, NewsAgent]


if __name__ == "__main__":
    run = asyncio.run(BriefingAgent.run("Tokyo"))
    print(run.result)
