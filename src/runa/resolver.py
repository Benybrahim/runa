from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from runa.runtime import Runtime


RuntimeFactory = Callable[[], "Runtime"]


class ModelResolver:
    """Resolve a model name to a runtime."""

    def __init__(self) -> None:
        self._models: dict[str, RuntimeFactory] = {}
        self._conventions: list[tuple[str, RuntimeFactory]] = []

    def register(self, model: str, factory: RuntimeFactory) -> None:
        self._models[model] = factory

    def register_convention(
        self,
        prefix: str,
        factory: RuntimeFactory,
    ) -> None:
        self._conventions.append((prefix, factory))

    def resolve(self, model: str) -> "Runtime":
        factory = self._models.get(model)

        if factory is not None:
            return factory()

        for prefix, factory in self._conventions:
            if model.startswith(prefix):
                return factory()

        raise ValueError(f"Unsupported model: {model}")