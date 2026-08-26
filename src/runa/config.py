from runa.resolver import ModelResolver


class Config:
    """Runa application configuration."""

    def __init__(self) -> None:
        self.resolver = ModelResolver()


config = Config()