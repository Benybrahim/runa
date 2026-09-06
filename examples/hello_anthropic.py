"""hello_anthropic.py: the smallest complete Runa app, on AnthropicProvider.

Identical to hello.py except for the Provider: swapping OpenAIProvider for
AnthropicProvider is the only change an app needs to switch model vendors
(manifesto §17: components are integrated through one Provider contract, not
wired together per vendor).

Requires ANTHROPIC_API_KEY in the environment.
Run with: uv run python examples/hello_anthropic.py
"""

from runa import Agent, AnthropicProvider, AsyncAnthropicProvider, configure, tool


@tool
def get_weather(city: str) -> str:
    return f"{city}: sunny, 22C"


class WeatherAgent(Agent):
    instructions = "Answer weather questions using the get_weather tool."
    tools = [get_weather]


if __name__ == "__main__":
    configure(provider=AnthropicProvider(), async_provider=AsyncAnthropicProvider())

    run = WeatherAgent.run_sync("What's the weather in Tokyo?")
    print(run.result)
