from runa.agent import Agent
from runa.providers.openai import OpenAIRuntime
from runa.resolver import ModelResolver


class Runa:
    """A Runa application."""

    def __init__(self) -> None:
        self.resolver = ModelResolver()

        self.resolver.register_convention(
            "gpt-",
            OpenAIRuntime,
        )

    def agent(
            self,
            *,
            name: str,
            instructions: str,
            model: str,
            tools: list[Callable[..., object]] | None = None,
    ) -> Agent:
        return Agent(
            name=name,
            instructions=instructions,
            model=model,
            tools=tools,
            _resolver=self.resolver,
        )


default_runa = Runa()