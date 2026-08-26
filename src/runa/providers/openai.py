from agents import Agent as OpenAIAgent
from agents import Runner

from runa.runtime import RuntimeResult


class OpenAIRuntime:
    """Runtime backed by the OpenAI Agents SDK."""

    def execute(
        self,
        *,
        instructions: str,
        input: str,
        model: str,
    ) -> RuntimeResult:
        agent = OpenAIAgent(
            name="Runa Agent",
            instructions=instructions,
            model=model,
        )

        result = Runner.run_sync(agent, input)

        return RuntimeResult(output=result.final_output)