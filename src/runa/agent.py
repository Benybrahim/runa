from runa.config import config
from runa.run import Run


class Agent:
    """An agentic application."""

    def __init__(
        self,
        *,
        name: str,
        instructions: str,
        model: str,
    ) -> None:
        self.name = name
        self.instructions = instructions
        self.model = model

    def run(self, input: str) -> Run:
        """Execute the agent."""
        runtime = config.resolver.resolve(self.model)

        result = runtime.execute(
            instructions=self.instructions,
            input=input,
            model=self.model,
        )

        return Run(output=result.output)