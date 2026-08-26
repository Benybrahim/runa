from dataclasses import dataclass


@dataclass
class FakeRuntime:
    response: str = "Hello from Runa."

    def execute(
        self,
        *,
        instructions: str,
        input: str,
    ) -> str:
        return self.response