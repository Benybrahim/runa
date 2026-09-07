"""`@tool` decorator for exposing functions to agents."""

from collections.abc import Awaitable, Callable
from typing import Any, overload

from agents import FunctionTool
from agents import function_tool as _function_tool

from runa.guardrail import ToolGuardrailsList, flatten_tool_guardrails

_ApprovalCheck = Callable[..., Awaitable[bool]]


@overload
def tool(func: Callable[..., Any]) -> FunctionTool: ...


@overload
def tool(
    func: None = None,
    *,
    guardrail: ToolGuardrailsList | None = None,
    require_approval: bool | _ApprovalCheck = False,
    **kwargs: Any,
) -> Callable[[Callable[..., Any]], FunctionTool]: ...


def tool(
    func: Callable[..., Any] | None = None,
    *,
    guardrail: ToolGuardrailsList | None = None,
    require_approval: bool | _ApprovalCheck = False,
    **kwargs: Any,
) -> FunctionTool | Callable[[Callable[..., Any]], FunctionTool]:
    """Wrap a function as a `FunctionTool`, adding `guardrail=[...]` and `require_approval=`.

    `guardrail` takes a flat list of `@guardrail` predicates bound via `.tool_input`/
    `.tool_output` (or a bare predicate, wired as both) — checked against the tool call's
    parsed arguments and its return value, respectively. `require_approval` forwards to the
    SDK's `needs_approval`. Every other keyword passes straight through to `function_tool`.
    """
    input_guardrails, output_guardrails = flatten_tool_guardrails(guardrail or [])
    decorator = _function_tool(
        tool_input_guardrails=input_guardrails or None,
        tool_output_guardrails=output_guardrails or None,
        needs_approval=require_approval,
        **kwargs,
    )
    return decorator(func) if func is not None else decorator


__all__ = ["tool"]
