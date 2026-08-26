from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from runa.runtime import Runtime


RuntimeFactory = Callable[[], "Runtime"]


class ModelResolver:
    """Resolve a model name to a runtime."""

    def __init__(self) -> None:
        self._models: dict[str, RuntimeFactory] = {}

    def register(self, model: str, factory: RuntimeFactory) -> None:
        self._models[model] = factory

    def resolve(self, model: str) -> "Runtime":
        try:
            factory = self._models[model]
        except KeyError:
            raise ValueError(f"Unsupported model: {model}") from None

        return factory()
