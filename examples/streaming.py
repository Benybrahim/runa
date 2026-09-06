"""streaming.py: print the model's answer as it streams in.

`Agent.run()` always returns one whole `Run`; for a chat-shaped consumer
that wants to show text as it's generated, `Agent.run_stream()` is the
opt-in path: it drives the exact same `Executor` loop, just observed as an
async iterator of `StreamChunk`s instead of only returning the completed
`Run` at the end. `stream.run` is that same `Run`, available immediately
and filling in as you iterate, so the Run's messages, events, and final
state end up identical to the non-streaming path.

Requires `model` to resolve to a `StreamingProvider` (both
`AnthropicProvider` and `OpenAIProvider` implement one). Requires
OPENAI_API_KEY in the environment. Run with: uv run python examples/streaming.py
"""

import asyncio

from runa import Agent, StreamChunk, tool


@tool
def get_weather(city: str) -> str:
    return f"{city}: sunny, 22C"


class WeatherAgent(Agent):
    model = "gpt-5-nano"
    instructions = "Answer weather questions using the get_weather tool."
    tools = [get_weather]


async def main() -> None:
    stream = WeatherAgent.run_stream("What's the weather in Tokyo?")
    async for chunk in stream:
        print(chunk.text, end="", flush=True)
    print()  # the streamed text has no trailing newline
    print("Final result:", stream.run.result)


if __name__ == "__main__":
    asyncio.run(main())
