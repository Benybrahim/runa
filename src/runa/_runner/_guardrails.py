"""_guardrails.py: running an agent's or tool's guardrails, raising on a tripwire."""

from __future__ import annotations

from typing import Any

from runa._runner._spans import _close_span, _new_span
from runa._runner._state import GuardrailResult
from runa._types import RunContextWrapper
from runa.exceptions import (
    InputGuardrailTripwireTriggered,
    OutputGuardrailTripwireTriggered,
    ToolInputGuardrailTripwireTriggered,
    ToolOutputGuardrailTripwireTriggered,
)
from runa.guardrail import ToolInputGuardrailContext, ToolInputGuardrailData
from runa.tool import FunctionTool
from runa.tracing._trace import Trace


async def _run_input_guardrails(
    agent: Any, context_wrapper: RunContextWrapper, turn_input: Any, trace: Trace, parent_id: str
) -> None:
    for guardrail in agent.input_guardrails:
        span = _new_span(trace, parent_id, guardrail.name or "guardrail", "guardrail")
        result = await guardrail.guardrail_function(context_wrapper, agent, turn_input)
        _close_span(span, error="tripwire triggered" if result.tripwire_triggered else None)
        if result.tripwire_triggered:
            raise InputGuardrailTripwireTriggered(GuardrailResult(guardrail, result))


async def _run_output_guardrails(
    agent: Any, context_wrapper: RunContextWrapper, output: Any, trace: Trace, parent_id: str
) -> None:
    for guardrail in agent.output_guardrails:
        span = _new_span(trace, parent_id, guardrail.name or "guardrail", "guardrail")
        result = await guardrail.guardrail_function(context_wrapper, agent, output)
        _close_span(span, error="tripwire triggered" if result.tripwire_triggered else None)
        if result.tripwire_triggered:
            raise OutputGuardrailTripwireTriggered(GuardrailResult(guardrail, result))


async def _run_tool_input_guardrails(
    tool: FunctionTool, args_json: str, call_id: str, trace: Trace, parent_id: str
) -> None:
    for guardrail in tool.tool_input_guardrails or []:
        span = _new_span(trace, parent_id, guardrail.get_name(), "guardrail")
        data = ToolInputGuardrailData(
            context=ToolInputGuardrailContext(tool_arguments=args_json, call_id=call_id)
        )
        result = await guardrail.guardrail_function(data)
        tripped = result.behavior["type"] == "raise_exception"
        _close_span(span, error="tripwire triggered" if tripped else None)
        if tripped:
            raise ToolInputGuardrailTripwireTriggered(guardrail, result)


async def _run_tool_output_guardrails(
    tool: FunctionTool, args_json: str, call_id: str, output: Any, trace: Trace, parent_id: str
) -> None:
    for guardrail in tool.tool_output_guardrails or []:
        span = _new_span(trace, parent_id, guardrail.get_name(), "guardrail")
        data = ToolInputGuardrailData(
            context=ToolInputGuardrailContext(tool_arguments=args_json, call_id=call_id),
            output=output,
        )
        result = await guardrail.guardrail_function(data)
        tripped = result.behavior["type"] == "raise_exception"
        _close_span(span, error="tripwire triggered" if tripped else None)
        if tripped:
            raise ToolOutputGuardrailTripwireTriggered(guardrail, result)


__all__ = [
    "_run_input_guardrails",
    "_run_output_guardrails",
    "_run_tool_input_guardrails",
    "_run_tool_output_guardrails",
]
