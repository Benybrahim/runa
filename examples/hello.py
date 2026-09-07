"""A minimal agent with a tool, a handoff, a delegate, and a guardrail."""

import re
from datetime import datetime

from runa import Agent, guardrail, tool

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


@guardrail
def block_empty(input: str) -> bool:
    """Trip when the user sends an empty message."""
    return not input.strip()


@guardrail
def block_long(output: str) -> bool:
    """Trip when the reply runs longer than 500 characters."""
    return len(output) > 500


@guardrail
def no_args(args: dict) -> bool:
    """Trip if `now` is somehow called with arguments."""
    return bool(args)


@tool(guardrail=[no_args.tool_input, block_long.tool_output])
def now() -> str:
    """Return the current local time as an ISO 8601 string."""
    return datetime.now().isoformat()


@guardrail
def contains_pii(text: str) -> bool:
    """Trip when the text contains an email address."""
    return bool(_EMAIL.search(text))


class Researcher(Agent):
    """Researches a topic and reports back findings."""

    name = "Researcher"
    instructions = "You research topics thoroughly and report back findings."


class Translator(Agent):
    """Translates text into French."""

    name = "Translator"
    instructions = "You translate text into French."


class Summarizer(Agent):
    """Summarizes text concisely."""

    name = "Summarizer"
    instructions = "You summarize text concisely."


class Assistant(Agent):
    """A friendly assistant that can delegate to a researcher, translator, or summarizer."""

    name = "Assistant"
    instructions = "You are a friendly assistant."
    tools = [now]
    subagents = [Researcher.handoff, Translator.delegate, Summarizer]
    guardrails = [block_empty.input, block_long.output, contains_pii]


agent = Assistant()
print(agent.run_sync("What time is it right now?"))
