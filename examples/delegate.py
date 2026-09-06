"""delegate.py: one agent delegating to another (manifesto §6).

`Agent.delegations` declares a sub-agent as a capability the model can call,
separately from `tools`: delegation reuses DefaultStrategy's existing
tool-use loop, no new Strategy needed. This is the Return outcome (the
default): the sub-agent runs to completion and its answer comes back as a
tool result. See `transfer_delegate.py` for the Transfer outcome, where the
sub-agent takes over the conversation instead.

A Return delegate runs its own nested Run, with its own Provider resolved
from its own `model`, independently of the delegating Agent's: both
`ResearchAgent` and `LeadAgent` declare one here.

Requires OPENAI_API_KEY in the environment.
Run with: uv run python examples/delegate.py
"""

from runa import Agent


class ResearchAgent(Agent):
    model = "gpt-5-nano"
    instructions = "Answer research questions concisely, citing no sources."


class LeadAgent(Agent):
    model = "gpt-5-nano"
    instructions = "Delegate research questions to the ResearchAgent tool."
    delegations = [ResearchAgent]


if __name__ == "__main__":
    run = LeadAgent.run_sync("What's promising about fusion energy right now?")
    print(run.result)
