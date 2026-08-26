from runa.config import config
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
        _resolver: ModelResolver | None = None,
    ) -> None:
        self.name = name
        self.instructions = instructions
        self.model = model
        self._resolver = _resolver or config.resolver

    def run(self, input: str) -> Run:
        """Execute the agent."""
        runtime = self._resolver.resolve(self.model)

        result = runtime.execute(
            instructions=self.instructions,
            input=input,
            model=self.model,
        )

        return Run(output=result.output)