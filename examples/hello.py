from runa import Agent


agent = Agent(
    name="assistant",
    instructions="Be helpful and concise.",
    model="gpt-5.6",
)

result = agent.run("What is Runa?")

print(result.output)