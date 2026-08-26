from runa.run import Run
from runa.runtime import Runtime


class Agent:
    """An agentic application."""

    def __init__(
        self,
        *,
        name: str,
        instructions: str,
        model: str,
        runtime: Runtime,
    ) -> None:
        self.name = name
        self.instructions = instructions
        self.model = model
        self.runtime = runtime

    def run(self, input: str) -> Run:
        """Execute the agent."""
        result = self.runtime.execute(
            instructions=self.instructions,
            input=input,
            model=self.model,
        )

        return Run(output=result.output)