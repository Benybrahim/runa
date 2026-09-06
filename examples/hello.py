"""hello.py: the smallest complete Runa app.

`model` alone is enough: Runa infers the Provider from the name (a
"gpt-"/"o"-prefixed model resolves to OpenAIProvider, see
`providers.registry.resolve_provider_for_model`), so no `configure()` call
is needed. Requires OPENAI_API_KEY in the environment. Run with `make hello`.
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
    run = WeatherAgent.run_sync("What's the weather in Tokyo?")
    print(run.result)
