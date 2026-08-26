from runa import Agent


def get_weather(city: str) -> str:
    """Get the weather for a city."""
    return f"The weather in {city} is sunny."


agent = Agent(
    name="assistant",
    instructions="Use tools when they are useful.",
    model="gpt-5.4-nano",
    tools=[get_weather],
)

result = agent.run("What's the weather in Tokyo?")

print(result.output)