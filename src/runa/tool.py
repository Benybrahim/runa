"""Tool: how agents interact with the world outside themselves."""

import inspect
from collections.abc import Callable
from typing import Any, get_type_hints

_JSON_TYPES: dict[type, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
}


def _json_type(annotation: Any) -> str:
    return _JSON_TYPES.get(annotation, "string")


def _schema_from_signature(
    func: Callable, *, skip_self: bool = False
) -> dict[str, Any]:
    signature = inspect.signature(func)
    hints = get_type_hints(func)
    properties: dict[str, Any] = {}
    required: list[str] = []

    for position, (param_name, param) in enumerate(signature.parameters.items()):
        if skip_self and position == 0:
            continue
        if param.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            continue
        properties[param_name] = {"type": _json_type(hints.get(param_name, str))}
        if param.default is inspect.Parameter.empty:
            required.append(param_name)

    return {"type": "object", "properties": properties, "required": required}


class Tool:
    """Base class for capabilities an Agent can invoke.

    Subclass and implement `call`. Name, description, and the parameter
    schema are derived from the class and its `call` method unless
    overridden explicitly:

        class WebSearch(Tool):
            def call(self, query: str):
                ...
    """

    name: str | None = None
    description: str = ""
    requires_approval: bool = False

    def call(self, **kwargs: Any) -> Any:
        raise NotImplementedError

    def tool_name(self) -> str:
        return self.name or type(self).__name__

    def tool_description(self) -> str:
        if self.description:
            return self.description
        call_doc = inspect.getdoc(type(self).call)
        if call_doc:
            return call_doc
        # `type(self).__doc__` (unlike inspect.getdoc on a class) is not
        # inherited from a base class, so an undocumented subclass of Tool
        # won't pick up Tool's own docstring here.
        class_doc = type(self).__doc__
        return inspect.cleandoc(class_doc) if class_doc else ""

    def schema(self) -> dict[str, Any]:
        return _schema_from_signature(type(self).call, skip_self=True)


class FunctionTool(Tool):
    """Adapts a plain function into a Tool."""

    def __init__(
        self,
        func: Callable,
        *,
        name: str | None = None,
        description: str | None = None,
        requires_approval: bool = False,
    ) -> None:
        self._func = func
        self.name = name or func.__name__
        self.description = description or (inspect.getdoc(func) or "")
        self.requires_approval = requires_approval
        self._schema = _schema_from_signature(func, skip_self=False)

    def call(self, **kwargs: Any) -> Any:
        return self._func(**kwargs)

    def schema(self) -> dict[str, Any]:
        return self._schema


def tool(
    func: Callable | None = None,
    *,
    name: str | None = None,
    description: str | None = None,
    requires_approval: bool = False,
) -> FunctionTool | Callable[[Callable], FunctionTool]:
    """Turn a plain function into a Tool.

    @tool
    def get_weather(city: str) -> str:
        return f"{city}: sunny"
    """

    def decorator(fn: Callable) -> FunctionTool:
        return FunctionTool(
            fn,
            name=name,
            description=description,
            requires_approval=requires_approval,
        )

    if func is not None:
        return decorator(func)
    return decorator
