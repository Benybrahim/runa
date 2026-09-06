"""delegate.py: one agent delegating to another (manifesto §6).

`Agent.delegations` declares a sub-agent as a capability the model can call,
separately from `tools`: delegation reuses DefaultStrategy's existing
tool-use loop, no new Strategy needed. This is the Return outcome (the
default): the sub-agent runs to completion and its answer comes back as a
tool result. See `transfer_delegate.py` for the Transfer outcome, where the
sub-agent takes over the conversation instead.

Requires OPENAI_API_KEY in the environment.
Run with: uv run python examples/delegate.py
"""

from runa import Agent, OpenAIProvider, configure


class ResearchAgent(Agent):
    instructions = "Answer research questions concisely, citing no sources."


class LeadAgent(Agent):
    instructions = "Delegate research questions to the ResearchAgent tool."
    delegations = [ResearchAgent]


if __name__ == "__main__":
    configure(provider=OpenAIProvider())

    run = LeadAgent.run_sync("What's promising about fusion energy right now?")
    print(run.result)
