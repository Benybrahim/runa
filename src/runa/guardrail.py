"""`@guardrail` decorator that turns a plain predicate into an input/output guardrail."""

import inspect
import json
from collections.abc import Awaitable, Callable
from typing import Any

from agents import (
    GuardrailFunctionOutput,
    InputGuardrail,
    OutputGuardrail,
    ToolGuardrailFunctionOutput,
    ToolInputGuardrail,
    ToolInputGuardrailData,
    ToolOutputGuardrail,
)
from agents.items import TResponseInputItem

_Predicate = Callable[[Any], bool | Awaitable[bool]]


def _latest_text(value: str | list[TResponseInputItem]) -> str:
    """Reduce a guardrail's raw input (a string, or the running item list) to the latest text."""
    if isinstance(value, str):
        return value
    content = value[-1].get("content", "") if value else ""
    if isinstance(content, list):
        content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
    return str(content)


def _wrap(
    func: _Predicate, *, reduce_input: bool
) -> Callable[..., Awaitable[GuardrailFunctionOutput]]:
    """Wrap a `(value) -> bool` predicate into the SDK's async `(ctx, agent, value)` shape."""

    async def wrapper(ctx: Any, agent: Any, value: Any) -> GuardrailFunctionOutput:
        checked = _latest_text(value) if reduce_input else value
        result = func(checked)
        if inspect.isawaitable(result):
            result = await result
        return GuardrailFunctionOutput(output_info=func.__doc__, tripwire_triggered=bool(result))

    return wrapper


def _tool_args(data: ToolInputGuardrailData) -> Any:
    """Parse a tool call's raw JSON arguments into a dict, falling back to the raw string."""
    try:
        return json.loads(data.context.tool_arguments)
    except TypeError, ValueError:
        return data.context.tool_arguments


def _wrap_tool(
    func: _Predicate, *, on_output: bool
) -> Callable[[Any], Awaitable[ToolGuardrailFunctionOutput]]:
    """Wrap a `(value) -> bool` predicate into a tool guardrail's async `(data)` shape."""

    async def wrapper(data: Any) -> ToolGuardrailFunctionOutput:
        checked = data.output if on_output else _tool_args(data)
        result = func(checked)
        if inspect.isawaitable(result):
            result = await result
        return (
            ToolGuardrailFunctionOutput.raise_exception(output_info=func.__doc__)
            if result
            else ToolGuardrailFunctionOutput.allow(output_info=func.__doc__)
        )

    return wrapper


class Guardrail:
    """A predicate bound to neither side yet; `.input`/`.output` picks which.

    `@guardrail` wraps a plain `(value) -> bool` predicate — tripping the guardrail on `True` —
    into this, the same way `@tool` wraps a plain function into a `FunctionTool`. Read `.input`
    to bind it as an `InputGuardrail` (the predicate always sees the latest user message as
    plain text, regardless of whether the SDK passed a string or the running list of input
    items) or `.output` to bind it as an `OutputGuardrail`, for an `Agent.guardrails` list.
    Read `.tool_input`/`.tool_output` to bind it as a `ToolInputGuardrail`/`ToolOutputGuardrail`
    instead, for a `@tool(guardrail=[...])` list — checked against the tool call's parsed
    arguments and its return value, respectively. The predicate's docstring becomes
    `output_info`. Listed bare (no binding), it's wired as both sides of whichever pair applies.
    """

    def __init__(self, func: _Predicate) -> None:
        """Store the predicate to bind on `.input`/`.output` access."""
        self._func = func

    @property
    def input(self) -> InputGuardrail[Any]:
        """Bind this predicate as an `InputGuardrail`."""
        return InputGuardrail(
            guardrail_function=_wrap(self._func, reduce_input=True), name=self._func.__name__
        )

    @property
    def output(self) -> OutputGuardrail[Any]:
        """Bind this predicate as an `OutputGuardrail`."""
        return OutputGuardrail(
            guardrail_function=_wrap(self._func, reduce_input=False), name=self._func.__name__
        )

    @property
    def tool_input(self) -> ToolInputGuardrail[Any]:
        """Bind this predicate as a `ToolInputGuardrail`, checked against the call's arguments."""
        return ToolInputGuardrail(
            guardrail_function=_wrap_tool(self._func, on_output=False), name=self._func.__name__
        )

    @property
    def tool_output(self) -> ToolOutputGuardrail[Any]:
        """Bind this predicate as a `ToolOutputGuardrail`, checked against the return value."""
        return ToolOutputGuardrail(
            guardrail_function=_wrap_tool(self._func, on_output=True), name=self._func.__name__
        )


def guardrail(func: _Predicate) -> Guardrail:
    """Turn a `(value) -> bool` predicate into a `Guardrail`; bind it via `.input`/`.output`."""
    return Guardrail(func)


ToolGuardrailsList = list["ToolInputGuardrail[Any] | ToolOutputGuardrail[Any] | Guardrail"]


def flatten_tool_guardrails(
    guardrails: ToolGuardrailsList,
) -> tuple[list[ToolInputGuardrail[Any]], list[ToolOutputGuardrail[Any]]]:
    """Split a `@tool(guardrail=[...])` list into input/output lists; bare entries wire as both."""
    input_guardrails: list[ToolInputGuardrail[Any]] = []
    output_guardrails: list[ToolOutputGuardrail[Any]] = []
    for entry in guardrails:
        if isinstance(entry, Guardrail):
            input_guardrails.append(entry.tool_input)
            output_guardrails.append(entry.tool_output)
        elif isinstance(entry, ToolInputGuardrail):
            input_guardrails.append(entry)
        elif isinstance(entry, ToolOutputGuardrail):
            output_guardrails.append(entry)
        else:
            raise TypeError(
                f"guardrail entries must be @guardrail predicates bound via "
                f".tool_input/.tool_output, got {type(entry).__name__}"
            )
    return input_guardrails, output_guardrails


__all__ = ["Guardrail", "flatten_tool_guardrails", "guardrail"]
