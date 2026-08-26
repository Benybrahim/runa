from typing import Protocol


class Runtime(Protocol):
    def execute(
        self,
        *,
        instructions: str,
        input: str,
    ) -> str:
        """Execute an agent run."""
