"""_tool_calls.py: executing one message's tool calls — handoffs, approval gating, guardrails."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from runa._runner._guardrails import _run_tool_input_guardrails, _run_tool_output_guardrails
from runa._runner._helpers import _agent_tools, _find_tool, _needs_approval, _normalized_handoffs
from runa._runner._spans import _close_span, _new_span
from runa._runner._state import Interruption
from runa._types import RunContextWrapper, TResponseInputItem
from runa.logging import RunHooks
from runa.tool import FunctionTool
from runa.tracing._trace import Trace


async def _run_tool_call(
    tool: FunctionTool,
    call: dict[str, Any],
    context_wrapper: RunContextWrapper,
    agent: Any,
    hooks: RunHooks[Any],
    trace: Trace,
    parent_id: str,
) -> TResponseInputItem:
    """Run one already-approved tool call end to end: guardrails, invocation, guardrails."""
    call_id = call["id"]
    args_json = call["function"]["arguments"] or "{}"
    span = _new_span(trace, parent_id, tool.name, "tool", input=args_json)
    await hooks.on_tool_start(context_wrapper, agent, tool)
    try:
        await _run_tool_input_guardrails(tool, args_json, call_id, trace, span.id)
        try:
            result = await tool.on_invoke_tool(context_wrapper, args_json, call_id)
            error: str | None = None
        except Exception as exc:  # noqa: BLE001 -- a tool failing is data, not a run-ending error
            result = f"error: {exc}"
            error = str(exc)
        await _run_tool_output_guardrails(tool, args_json, call_id, result, trace, span.id)
    except BaseException:
        _close_span(span, error="tool guardrail tripwire triggered")
        raise
    _close_span(span, error=error, output=result)
    await hooks.on_tool_end(context_wrapper, agent, tool, result)
    return {"role": "tool", "tool_call_id": call_id, "content": str(result)}


@dataclass
class _TurnOutcome:
    final_output: str | None
    generated: list[TResponseInputItem]
    interruptions: list[Interruption]
    ready_results: list[TResponseInputItem]
    current_agent: Any


async def _run_message_tool_calls(
    message: dict[str, Any],
    current_agent: Any,
    context_wrapper: RunContextWrapper,
    hooks: RunHooks[Any],
    trace: Trace,
    parent_id: str,
    approvals: dict[str, bool] | None,
) -> tuple[list[TResponseInputItem], list[Interruption], Any]:
    """Execute (or defer for approval) every tool call in `message`; returns results so far."""
    handoff_map = _normalized_handoffs(getattr(current_agent, "handoffs", []))
    tools = await _agent_tools(current_agent)
    results: list[TResponseInputItem] = []
    interruptions: list[Interruption] = []
    switched_agent: Any = None
    approvals = approvals or {}

    for call in message.get("tool_calls") or []:
        name = call["function"]["name"]
        call_id = call["id"]
        if name in handoff_map:
            handoff = handoff_map[name]
            switched_agent = handoff.agent
            span = _new_span(trace, parent_id, handoff.tool_name, "handoff")
            _close_span(span)
            await hooks.on_handoff(context_wrapper, current_agent, switched_agent)
            results.append(
                {
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": f"Transferred to {switched_agent.name}.",
                }
            )
            continue

        tool = _find_tool(tools, name)
        if tool is None:
            results.append(
                {"role": "tool", "tool_call_id": call_id, "content": f"error: unknown tool {name}"}
            )
            continue

        args_json = call["function"]["arguments"] or "{}"
        args = json.loads(args_json) if args_json else {}
        if await _needs_approval(tool, context_wrapper, args, call_id):
            verdict = approvals.get(call_id)
            if verdict is None:
                interruptions.append(
                    Interruption(
                        name=name,
                        arguments=args_json,
                        call_id=call_id,
                        tool=tool,
                        agent=current_agent,
                    )
                )
                continue
            if verdict is False:
                results.append(
                    {"role": "tool", "tool_call_id": call_id, "content": "rejected by the operator"}
                )
                continue

        results.append(
            await _run_tool_call(
                tool, call, context_wrapper, current_agent, hooks, trace, parent_id
            )
        )

    return results, interruptions, switched_agent


__all__ = ["_TurnOutcome", "_run_message_tool_calls", "_run_tool_call"]
