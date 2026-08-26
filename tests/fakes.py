from collections.abc import Callable
from dataclasses import dataclass
from runa.runtime import RuntimeResult

@dataclass
class FakeRuntime:
    response: str = "Hello from Runa."
    received_tools: list[Callable[..., object]] | None = None

    def execute(
        self,
        *,
        instructions: str,
        input: str,
        model: str,
        tools: list[Callable[..., object]],
    ) -> RuntimeResult:
        self.received_tools = tools
        return RuntimeResult(output=self.response)