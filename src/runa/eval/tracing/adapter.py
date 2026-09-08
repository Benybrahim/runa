"""eval/tracing/adapter.py: run one `Case` through an `Agent` and normalize the result.

The OpenAI Agents SDK's `RunResult` is the source of truth for what an agent
run actually did; this module reads it (never builds a parallel tracing
abstraction) and flattens it to the handful of fields the evaluators in
`eval/evaluation/` need: final output, tool calls, whether it errored, and
how long it took.
"""

import time
from dataclasses import dataclass, field
from typing import Any

from agents import Runner
from agents.exceptions import AgentsException
from agents.items import ToolCallItem, ToolCallOutputItem

from runa.agent import _RUN_CONFIG, Agent
from runa.eval.case import Case


@dataclass
class ToolCallRecord:
    """One tool call an agent made during a run, paired with its output."""

    name: str
    arguments: str
    output: str | None = None


@dataclass
class AgentRun:
    """A `Case`'s input run through an `Agent`, normalized for evaluation."""

    input: str
    final_output: str | None
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    error: str | None = None
    latency: float = 0.0


async def run_agent_for_eval(agent: Agent, case: Case) -> AgentRun:
    """Run `case.input` through `agent` and capture an `AgentRun`.

    A run that raises (a guardrail tripwire, `MaxTurnsExceeded`, ...) is
    captured as an `AgentRun` with `error` set rather than propagating, so a
    bad case doesn't stop the rest of a dataset from evaluating.
    """
    start = time.monotonic()
    try:
        result = await Runner.run(agent, case.input, run_config=_RUN_CONFIG)
    except AgentsException as exc:
        return AgentRun(
            input=case.input, final_output=None, error=str(exc), latency=time.monotonic() - start
        )
    latency = time.monotonic() - start

    outputs_by_call_id: dict[str, Any] = {}
    for item in result.new_items:
        if isinstance(item, ToolCallOutputItem) and item.call_id is not None:
            outputs_by_call_id[item.call_id] = item.output

    tool_calls = []
    for item in result.new_items:
        if isinstance(item, ToolCallItem):
            call_id = getattr(item.raw_item, "call_id", None)
            tool_calls.append(
                ToolCallRecord(
                    name=item.tool_name or "",
                    arguments=getattr(item.raw_item, "arguments", ""),
                    output=str(outputs_by_call_id[call_id])
                    if call_id in outputs_by_call_id
                    else None,
                )
            )

    return AgentRun(
        input=case.input,
        final_output=result.final_output,
        tool_calls=tool_calls,
        latency=latency,
    )
