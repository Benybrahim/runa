"""`@tool` decorator for exposing functions to agents."""

from collections.abc import Callable
from typing import Any, overload

from agents import FunctionTool
from agents import function_tool as _function_tool

from runa.guardrail import ToolGuardrailsDict, ToolGuardrailsList, flatten_tool_guardrails


@overload
def tool(func: Callable[..., Any]) -> FunctionTool: ...


@overload
def tool(
    func: None = None,
    *,
    guardrail: ToolGuardrailsList | ToolGuardrailsDict | None = None,
    **kwargs: Any,
) -> Callable[[Callable[..., Any]], FunctionTool]: ...


def tool(
    func: Callable[..., Any] | None = None,
    *,
    guardrail: ToolGuardrailsList | ToolGuardrailsDict | None = None,
    **kwargs: Any,
) -> FunctionTool | Callable[[Callable[..., Any]], FunctionTool]:
    """Wrap a function as a `FunctionTool`, adding a `guardrail=[...]` (or `{...}`) list.

    Accepts native `ToolInputGuardrail`/`ToolOutputGuardrail`, a bare `@guardrail` predicate
    (wired as both), or the same `.input`/`.output`-bound predicate used for `Agent.guardrails`
    — reused here against the tool call's parsed arguments and its return value, respectively.
    Everything else, including `needs_approval`, passes straight through to `function_tool`.
    """
    input_guardrails, output_guardrails = flatten_tool_guardrails(guardrail or [])
    decorator = _function_tool(
        tool_input_guardrails=input_guardrails or None,
        tool_output_guardrails=output_guardrails or None,
        **kwargs,
    )
    return decorator(func) if func is not None else decorator


__all__ = ["tool"]
