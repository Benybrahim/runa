"""A minimal agent with a tool, a handoff, a delegate, and a guardrail."""

import re
from dataclasses import dataclass
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


@dataclass
class Context:
    """Per-run data threaded into `Assistant.instructions` below."""

    user_name: str


def instructions(context: Context) -> str:
    """Greet the user by name, resolved fresh on every run from `Agent.run`'s `context=`."""
    return f"You are a friendly assistant helping {context.user_name}."


@guardrail
def no_args(args: dict) -> bool:
    """Trip if `now` is somehow called with arguments."""
    return bool(args)


@guardrail
def log_call(value: object) -> bool:
    """Print the value seen on either side of the call, but never trip."""
    print(f"now(): {value!r}")
    return False


@tool(guardrail=[no_args.input, block_long.output, log_call])
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


class MyAgent(Agent):
    """A friendly assistant that can delegate to a researcher, translator, or summarizer."""

    name = "assistant_agent"
    instructions = instructions
    tools = [now]
    subagents = [Researcher.handoff, Translator.delegate, Summarizer]
    guardrails = [block_empty.input, block_long.output, contains_pii]


agent = Assistant()
run = agent.run_sync("What time is it right now?")
#, context=Context(user_name="Ada"))
print(run.output)
