"""transfer_delegate.py: handing off a conversation to a specialist agent.

Every delegation's tool schema accepts an optional `transfer` flag alongside
`input`: the model decides per call whether to just get an answer back
(Return, the default, see `delegate.py`) or hand off the rest of the
conversation to the sub-agent (Transfer). A transfer doesn't spawn a nested
Run: the delegated Agent becomes the one driving this same Run, so its own
instructions take over for the rest of the exchange (see
`Executor._transfer`/`transfer_agent`).

Requires OPENAI_API_KEY in the environment.
Run with: uv run python examples/transfer_delegate.py
"""

from runa import Agent, OpenAIProvider, configure


class BillingAgent(Agent):
    instructions = "Help with billing questions: invoices, refunds, payment methods."


class TechSupportAgent(Agent):
    instructions = "Help debug technical issues with the product."


class TriageAgent(Agent):
    instructions = (
        "Figure out whether the customer's issue is a billing question or a "
        "technical problem, then transfer to the matching specialist. Don't "
        "try to answer the question yourself."
    )
    delegations = [BillingAgent, TechSupportAgent]


if __name__ == "__main__":
    configure(provider=OpenAIProvider())

    run = TriageAgent.run("I was charged twice for my subscription this month.")
    print(run.result)
    print(f"handled by: {run.active_agent_name}")
