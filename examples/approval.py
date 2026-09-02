"""approval.py: gate a sensitive tool behind a human decision.

`requires_approval` pauses the Run into AWAITING_APPROVAL instead of
executing the tool call; `approve()`/`deny()` resume it. This uses the
Executor/Run primitives directly rather than `Agent.run()`, since resuming
a paused Run means driving the *same* Run object again, not creating a new
one from input.

Requires OPENAI_API_KEY in the environment.
Run with: uv run python examples/approval.py
"""

from runa import (
    Agent,
    Executor,
    OpenAIProvider,
    Run,
    RunStatus,
    approve,
    tool,
)


@tool(requires_approval=True)
def send_refund(order_id: str, amount: float) -> str:
    return f"refunded ${amount:.2f} for order {order_id}"


class SupportAgent(Agent):
    instructions = "Help resolve support issues. Use send_refund when appropriate."
    tools = [send_refund]


if __name__ == "__main__":
    executor = Executor(provider=OpenAIProvider())
    agent = SupportAgent()

    run = executor.run(agent, Run(input="Refund order A123 for $42."))

    if run.status == RunStatus.AWAITING_APPROVAL:
        pending = next(tc for tc in run.tool_calls if not tc.completed)
        print(f"approval requested: {pending.name}({pending.arguments})")

        approve(run, pending.id)
        run = executor.run(agent, run)

    print(run.status, run.result)
