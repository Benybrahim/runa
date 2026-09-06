"""transfer_delegate.py: handing off a conversation to a specialist agent.

Every delegation's tool schema accepts an optional `transfer` flag alongside
`input`: the model decides per call whether to just get an answer back
(Return, the default, see `delegate.py`) or hand off the rest of the
conversation to the sub-agent (Transfer). A transfer doesn't spawn a nested
Run: the delegated Agent becomes the one driving this same Run, so its own
instructions take over for the rest of the exchange (see
`runtime._shared.transfer_agent`).

Because it's the same Run throughout, only `TriageAgent`, the one that
starts it, needs a `model`: that's what resolves the Provider the whole Run
uses, before any transfer happens. `BillingAgent`/`TechSupportAgent` don't
need their own, unlike a Return delegate (see `delegate.py`), which runs an
independent nested Run and resolves its own Provider from its own `model`.

Requires OPENAI_API_KEY in the environment.
Run with: uv run python examples/transfer_delegate.py
"""

from runa import Agent


class BillingAgent(Agent):
    instructions = "Help with billing questions: invoices, refunds, payment methods."


class TechSupportAgent(Agent):
    instructions = "Help debug technical issues with the product."


class TriageAgent(Agent):
    model = "gpt-5-nano"
    instructions = (
        "Figure out whether the customer's issue is a billing question or a "
        "technical problem, then transfer to the matching specialist. Don't "
        "try to answer the question yourself."
    )
    delegations = [BillingAgent, TechSupportAgent]


if __name__ == "__main__":
    run = TriageAgent.run_sync("I was charged twice for my subscription this month.")
    print(run.result)
    print(f"handled by: {run.active_agent_name}")
