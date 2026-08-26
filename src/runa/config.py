from runa.providers.openai import OpenAIRuntime
from runa.resolver import ModelResolver


class Config:
    """Runa application configuration."""

    def __init__(self) -> None:
        self.resolver = ModelResolver()

        self.resolver.register_convention(
            "gpt-",
            OpenAIRuntime,
        )


config = Config()