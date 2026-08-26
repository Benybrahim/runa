from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class RuntimeResult:
    output: str


class Runtime(Protocol):
    def execute(
        self,
        *,
        instructions: str,
        input: str,
        model: str,
    ) -> RuntimeResult:
        """Execute an agent run."""
