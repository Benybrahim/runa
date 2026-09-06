"""streaming.py: print the model's answer as it streams in.

`Provider.complete()` always returns one whole `Message`; for a chat-shaped
consumer that wants to show text as it's generated, `Executor.run(...,
on_chunk=...)` is the opt-in path: pass a `StreamingProvider` (both
`AnthropicProvider` and `OpenAIProvider` implement one) and a callback.
The Run's messages, events, and final state end up identical to the
non-streaming path; `on_chunk` only changes what's observed while a
CallModel step is in flight, so it composes with tools, retries, and
approval exactly like the plain `run()` does.

Requires OPENAI_API_KEY in the environment.
Run with: uv run python examples/streaming.py
"""

import asyncio

from runa import Agent, Executor, OpenAIProvider, Run, StreamChunk, tool


@tool
def get_weather(city: str) -> str:
    return f"{city}: sunny, 22C"


class WeatherAgent(Agent):
    instructions = "Answer weather questions using the get_weather tool."
    tools = [get_weather]


def print_as_it_arrives(chunk: StreamChunk) -> None:
    print(chunk.text, end="", flush=True)


if __name__ == "__main__":
    executor = Executor(OpenAIProvider())

    run = asyncio.run(
        executor.run(
            WeatherAgent(),
            Run(input="What's the weather in Tokyo?"),
            on_chunk=print_as_it_arrives,
        )
    )
    print()  # the streamed text has no trailing newline
    print("Final result:", run.result)
