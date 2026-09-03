"""parallel_delegate.py: two sub-agents delegated to concurrently (manifesto §6).

`Agent.as_async_tool()` is the async counterpart to `as_tool()`: its
DelegateTool runs the sub-agent through AsyncExecutor instead of a thread, so
when a model turn requests both sub-agents at once, AsyncExecutor's existing
concurrent tool-call batching (see AsyncExecutor's docstring) runs them as
genuine concurrent async I/O rather than one network call at a time.

Requires OPENAI_API_KEY in the environment.
Run with: uv run python examples/parallel_delegate.py
"""

import asyncio

from runa import Agent, AsyncOpenAIProvider, OpenAIProvider, configure


class WeatherAgent(Agent):
    instructions = "Answer weather questions concisely."


class NewsAgent(Agent):
    instructions = "Summarize one plausible top headline for a city, concisely."


class BriefingAgent(Agent):
    instructions = (
        "Given a city, call both WeatherAgent and NewsAgent, then combine "
        "their answers into a short morning briefing."
    )
    tools = [WeatherAgent.as_async_tool(), NewsAgent.as_async_tool()]


if __name__ == "__main__":
    configure(provider=OpenAIProvider(), async_provider=AsyncOpenAIProvider())

    run = asyncio.run(BriefingAgent.run_async("Tokyo"))
    print(run.result)
