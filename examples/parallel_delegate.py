"""parallel_delegate.py: two sub-agents delegated to concurrently (manifesto §6).

`AsyncDelegateAgent` is the concurrency-capable delegation for
`Agent.delegations`: it runs the sub-agent through AsyncExecutor instead of a
thread, so when a model turn requests both sub-agents at once, AsyncExecutor's
existing concurrent tool-call batching (see AsyncExecutor's docstring) runs
them as genuine concurrent async I/O rather than one network call at a time.
A bare class in `delegations` (e.g. `delegations = [WeatherAgent]`) still
works under AsyncExecutor, just via a thread per delegate instead.

Requires OPENAI_API_KEY in the environment.
Run with: uv run python examples/parallel_delegate.py
"""

import asyncio

from runa import (
    Agent,
    AsyncDelegateAgent,
    AsyncOpenAIProvider,
    OpenAIProvider,
    configure,
)


class WeatherAgent(Agent):
    instructions = "Answer weather questions concisely."


class NewsAgent(Agent):
    instructions = "Summarize one plausible top headline for a city, concisely."


class BriefingAgent(Agent):
    instructions = (
        "Given a city, call both WeatherAgent and NewsAgent, then combine "
        "their answers into a short morning briefing."
    )
    # No `executor=` override: both fall back to the app-wide default
    # AsyncProvider set by `configure()` below.
    delegations = [AsyncDelegateAgent(WeatherAgent), AsyncDelegateAgent(NewsAgent)]


if __name__ == "__main__":
    configure(provider=OpenAIProvider(), async_provider=AsyncOpenAIProvider())

    run = asyncio.run(BriefingAgent.run_async("Tokyo"))
    print(run.result)
