"""Tool: how agents interact with the world outside themselves."""

import dataclasses
import enum
import inspect
import types
from collections.abc import Callable
from typing import (
    Any,
    Protocol,
    Union,
    get_args,
    get_origin,
    get_type_hints,
    overload,
    runtime_checkable,
)

_JSON_TYPES: dict[type, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
}
_ARRAY_ORIGINS = (list, set, frozenset, tuple)


def _unwrap_optional(annotation: Any) -> Any:
    """Strip `X | None` / `Optional[X]` down to X, so its schema is X's schema."""
    if get_origin(annotation) in (Union, types.UnionType):
        args = [arg for arg in get_args(annotation) if arg is not type(None)]
        if len(args) == 1:
            return args[0]
    return annotation


def _dataclass_schema(cls: type) -> dict[str, Any]:
    hints = get_type_hints(cls)
    properties: dict[str, Any] = {}
    required: list[str] = []
    for field in dataclasses.fields(cls):
        properties[field.name] = _type_schema(hints.get(field.name, str))
        if (
            field.default is dataclasses.MISSING
            and field.default_factory is dataclasses.MISSING
        ):
            required.append(field.name)
    return {"type": "object", "properties": properties, "required": required}


def _type_schema(annotation: Any) -> dict[str, Any]:
    """Map a type annotation to a JSON Schema fragment, recursively.

    Handles the shapes manifesto §9's "structured inputs" implies beyond
    flat scalars: `list[T]` (recurses into `T`), `X | None` (unwraps to
    `X`), `Enum` subclasses (an enum of their values), and dataclasses
    (a nested object built from their fields). Anything else (a bare
    `list`/`dict` with no type args, `Any`, an unrecognized annotation)
    falls back to "string", the same default as before.
    """
    annotation = _unwrap_optional(annotation)
    origin = get_origin(annotation) or annotation

    if origin in _ARRAY_ORIGINS:
        args = get_args(annotation)
        items = _type_schema(args[0]) if args else {"type": "string"}
        return {"type": "array", "items": items}

    if origin is dict:
        return {"type": "object"}

    if isinstance(origin, type) and issubclass(origin, enum.Enum):
        values = [member.value for member in origin]
        value_type = _JSON_TYPES.get(type(values[0]), "string") if values else "string"
        return {"type": value_type, "enum": values}

    if isinstance(origin, type) and dataclasses.is_dataclass(origin):
        return _dataclass_schema(origin)

    return {"type": _JSON_TYPES.get(origin, "string")}


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
        properties[param_name] = _type_schema(hints.get(param_name, str))
        if param.default is inspect.Parameter.empty:
            required.append(param_name)

    return {"type": "object", "properties": properties, "required": required}


@runtime_checkable
class ParentRunAware(Protocol):
    """A Tool that wants to know which Run it's being called from.

    A separate, optional protocol, like `StreamingProvider`/`DurableQueue`
    elsewhere in Runa, not a method every Tool must implement. `Executor`
    calls `bind_parent_run_id()` right before `call()` for any Tool that
    satisfies this, structurally, with no base class to opt into.
    `DelegateAgent`/`AsyncDelegateAgent` (see agent.py) use it to stamp the
    sub-agent's Run with `parent_run_id`, so delegation lineage
    (architecture.md §15) survives being written to a RunStore and read back
    later, not just while the parent tool instance stays in memory.

    Deliberately narrower than handing a Tool the whole parent `Run`: a
    delegate only needs the parent's id for lineage, not read access to its
    state or messages (manifesto §8, "intelligence does not imply
    authority").
    """

    def bind_parent_run_id(self, run_id: str) -> None: ...


@runtime_checkable
class DelegatesToAgent(Protocol):
    """A Tool that wraps an Agent as a delegation (see `Agent.delegations`).

    Structural, like `ParentRunAware` above: `DelegateAgent`/
    `AsyncDelegateAgent` (agent.py) satisfy it without `Executor` needing
    to import agent.py directly (agent.py already imports `Executor`, so
    that import would cycle). `Executor` uses it to detect a
    `transfer=true` call and hand off the active Agent instead of running
    `call()` normally, via `new_agent_instance()`; see
    `runtime._shared.transfer_agent`.
    """

    def new_agent_instance(self) -> Any: ...


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
    idempotent: bool = False  # safe to retry on error, see runtime/retry.py

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
        idempotent: bool = False,
    ) -> None:
        self._func = func
        self.name = name or func.__name__
        self.description = description or (inspect.getdoc(func) or "")
        self.requires_approval = requires_approval
        self.idempotent = idempotent
        self._schema = _schema_from_signature(func, skip_self=False)

    def call(self, **kwargs: Any) -> Any:
        return self._func(**kwargs)

    def schema(self) -> dict[str, Any]:
        return self._schema


@overload
def tool(func: Callable) -> FunctionTool: ...


@overload
def tool(
    func: None = None,
    *,
    name: str | None = None,
    description: str | None = None,
    requires_approval: bool = False,
    idempotent: bool = False,
) -> Callable[[Callable], FunctionTool]: ...


def tool(
    func: Callable | None = None,
    *,
    name: str | None = None,
    description: str | None = None,
    requires_approval: bool = False,
    idempotent: bool = False,
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
            idempotent=idempotent,
        )

    if func is not None:
        return decorator(func)
    return decorator
