from collections.abc import Callable
from uuid import uuid4

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
        tools: list[Callable[..., object]] | None = None,
        _resolver: ModelResolver | None = None,
    ) -> None:
        self.name = name
        self.instructions = instructions
        self.model = model
        self.tools = tools or []
        self._resolver = _resolver

    def run(self, input: str) -> Run:
        """Execute the agent."""
        if self._resolver is None:
            from runa.runa import default_runa

            resolver = default_runa.resolver
        else:
            resolver = self._resolver

        runtime = resolver.resolve(self.model)

        result = runtime.execute(
            instructions=self.instructions,
            input=input,
            model=self.model,
            tools=self.tools,
        )

        return Run(
            id=str(uuid4()),
            output=result.output,
        )