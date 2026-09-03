"""plan_and_review.py: a planning + reflection agent, using existing hooks.

Manifesto §6 lists `plan()` and `review()` as opt-in Agent hooks without
prescribing what they do. This is a concrete reference for both: `plan()`
asks the model for a short plan before the tool-use loop starts, records it
as a PlanArtifact, and feeds it back into the conversation as a system
message so later steps see it. `review()` asks the model to check the
draft answer against that plan and returns a (possibly revised) final
answer — the Executor uses whatever `review()` returns in place of the
Strategy's draft result, instead of discarding it.

Neither hook needs a new integration: both call the same Provider the Run
itself runs on (manifesto §17), via the module-level `provider` below.

Requires OPENAI_API_KEY in the environment.
Run with: uv run python examples/plan_and_review.py
"""

from runa import (
    Agent,
    Message,
    OpenAIProvider,
    PlanArtifact,
    Role,
    Run,
    configure,
    tool,
)


@tool
def search(query: str) -> str:
    return f"3 sources on {query!r}: overview.example, data.example, review.example"


provider = OpenAIProvider()  # shared by the Run and the plan()/review() hooks


class ResearchAgent(Agent):
    instructions = """
    Research the question using the search tool, then answer concisely,
    citing which sources you used.
    """
    tools = [search]

    def plan(self, run: Run) -> None:
        plan = provider.complete(
            messages=[
                Message(
                    role=Role.USER,
                    content=f"In 2-3 short steps, plan how to research: {run.input!r}",
                )
            ],
            tools=[],
            model=self.model,
        ).content
        run.state.plan = plan
        run.add_artifact(PlanArtifact(steps=plan.splitlines()))
        run.add_message(Message(role=Role.SYSTEM, content=f"Plan:\n{plan}"))

    def review(self, run: Run) -> str:
        draft = run.messages[-1].content
        revised = provider.complete(
            messages=[
                *run.messages,
                Message(
                    role=Role.USER,
                    content=(
                        "Does the draft answer follow the plan above and fully "
                        "address the question? Reply with only the final answer, "
                        "revised if it needs to be."
                    ),
                ),
            ],
            tools=[],
            model=self.model,
        ).content
        return revised or draft


if __name__ == "__main__":
    configure(provider=provider)

    run = ResearchAgent.run("What are the most promising approaches to fusion energy?")
    print("Plan:\n", run.state.plan)
    print("\nResult:\n", run.result)
