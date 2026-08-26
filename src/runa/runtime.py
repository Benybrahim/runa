from collections.abc import Callable
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
        tools: list[Callable[..., object]],
    ) -> RuntimeResult:
        """Execute an agent run."""