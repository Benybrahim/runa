"""`@guardrail` decorator that turns a plain predicate into an input/output guardrail."""

import inspect
from collections.abc import Awaitable, Callable
from typing import Any

from agents import GuardrailFunctionOutput, InputGuardrail, OutputGuardrail
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


class Guardrail:
    """A predicate bound to neither side yet; `.input`/`.output` picks which.

    `@guardrail` wraps a plain `(value) -> bool` predicate — tripping the guardrail on `True` —
    into this, the same way `@tool` wraps a plain function into a `FunctionTool`. Read `.input`
    to bind it as an `InputGuardrail` (the predicate always sees the latest user message as
    plain text, regardless of whether the SDK passed a string or the running list of input
    items) or `.output` to bind it as an `OutputGuardrail`. The predicate's docstring becomes
    `output_info`.
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


def guardrail(func: _Predicate) -> Guardrail:
    """Turn a `(value) -> bool` predicate into a `Guardrail`; bind it via `.input`/`.output`."""
    return Guardrail(func)


__all__ = ["Guardrail", "guardrail"]
