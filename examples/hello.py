import asyncio
from datetime import datetime

from runa import Agent, tool


@tool
def now() -> str:
    return datetime.now().isoformat()


class Researcher(Agent):
    name = "Researcher"
    instructions = "You research topics thoroughly and report back findings."


class Translator(Agent):
    name = "Translator"
    instructions = "You translate text into French."


class Assistant(Agent):
    name = "Assistant"
    instructions = "You are a friendly assistant."
    tools = [now]
    subagents = [Researcher.handoff, Translator.delegate]


async def main() -> None:
    agent = Assistant()
    print(await agent.run("What time is it right now?"))


asyncio.run(main())
