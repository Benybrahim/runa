from dataclasses import dataclass

from runa.runtime import RuntimeResult


@dataclass
class FakeRuntime:
    response: str = "Hello from Runa."

    def execute(
        self,
        *,
        instructions: str,
        input: str,
        model: str,
    ) -> RuntimeResult:
        return RuntimeResult(output=self.response)