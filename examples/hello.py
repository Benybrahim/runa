"""hello.py: the smallest complete Runa app.

Requires OPENAI_API_KEY in the environment. Run with `make hello`.
"""

from runa import Agent, AsyncOpenAIProvider, OpenAIProvider, configure, tool


@tool
def get_weather(city: str) -> str:
    return f"{city}: sunny, 22C"


class WeatherAgent(Agent):
    instructions = "Answer weather questions using the get_weather tool."
    tools = [get_weather]


if __name__ == "__main__":
    configure(provider=OpenAIProvider(), async_provider=AsyncOpenAIProvider())

    run = WeatherAgent.run_sync("What's the weather in Tokyo?")
    print(run.result)
