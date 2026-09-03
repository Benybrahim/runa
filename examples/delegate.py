"""delegate.py: one agent delegating to another (manifesto §6).

`Agent.as_tool()` wraps an Agent as an ordinary Tool: the parent agent
declares it in `tools` like any other capability, and delegation reuses
DefaultStrategy's existing tool-use loop — no new Strategy needed.

Requires OPENAI_API_KEY in the environment.
Run with: uv run python examples/delegate.py
"""

from runa import Agent, OpenAIProvider, configure


class ResearchAgent(Agent):
    instructions = "Answer research questions concisely, citing no sources."


class LeadAgent(Agent):
    instructions = "Delegate research questions to the ResearchAgent tool."
    tools = [ResearchAgent.as_tool()]


if __name__ == "__main__":
    configure(provider=OpenAIProvider())

    run = LeadAgent.run("What's promising about fusion energy right now?")
    print(run.result)
