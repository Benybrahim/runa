from runa.run import Run
from runa.runtime import Runtime


class Agent:
    """An agentic application."""

    def __init__(
        self,
        *,
        name: str,
        instructions: str,
        runtime: Runtime,
    ) -> None:
        self.name = name
        self.instructions = instructions
        self.runtime = runtime

    def run(self, input: str) -> Run:
        """Execute the agent."""
        output = self.runtime.execute(
            instructions=self.instructions,
            input=input,
        )

        return Run(output=output)
