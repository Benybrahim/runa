from runa.resolver import ModelResolver
from runa.run import Run


class Agent:
    """An agentic application."""

    def __init__(
        self,
        *,
        name: str,
        instructions: str,
        model: str,
        resolver: ModelResolver,
    ) -> None:
        self.name = name
        self.instructions = instructions
        self.model = model
        self.resolver = resolver

    def run(self, input: str) -> Run:
        """Execute the agent."""
        runtime = self.resolver.resolve(self.model)

        result = runtime.execute(
            instructions=self.instructions,
            input=input,
            model=self.model,
        )

        return Run(output=result.output)
