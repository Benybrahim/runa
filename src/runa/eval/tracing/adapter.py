"""eval/tracing/adapter.py: run one `Case` through an `Agent` and normalize the result.

Uses the same `capture_trace` mechanism as `Agent.run`/`run_sync` (`runa/tracing/runner.py`), so
evaluation and observability read the same `Trace`/`Span` data instead of two parallel
execution-history models: `AgentRun.tool_calls` is derived straight from `AgentRun.trace.spans`.
"""

import time
from dataclasses import dataclass, field, replace

from agents import Runner
from agents.exceptions import AgentsException

from runa.agent import _RUN_CONFIG, Agent
from runa.eval.case import Case
from runa.tracing import Trace
from runa.tracing.runner import capture_trace

_EMPTY_TRACE = Trace(id="", name="", start_time=0.0, end_time=0.0, spans=[], metadata={})


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
    trace: Trace = field(default_factory=lambda: _EMPTY_TRACE)


async def run_agent_for_eval(agent: Agent, case: Case) -> AgentRun:
    """Run `case.input` through `agent` and capture an `AgentRun`.

    A run that raises (a guardrail tripwire, `MaxTurnsExceeded`, ...) is
    captured as an `AgentRun` with `error` set rather than propagating, so a
    bad case doesn't stop the rest of a dataset from evaluating.
    """
    start = time.monotonic()
    error: AgentsException | None = None
    result = None
    with capture_trace(workflow_name=type(agent).__name__) as cap:
        try:
            result = await Runner.run(
                agent, case.input, run_config=replace(_RUN_CONFIG, **cap.run_config_fields)
            )
        except AgentsException as exc:
            error = exc
    latency = time.monotonic() - start

    if error is not None or result is None:
        assert error is not None
        return AgentRun(
            input=case.input, final_output=None, error=str(error), latency=latency, trace=cap.trace
        )

    tool_calls = [
        ToolCallRecord(
            name=span.name,
            arguments=span.input or "",
            output=str(span.output) if span.output is not None else None,
        )
        for span in cap.trace.spans
        if span.type == "tool"
    ]
    return AgentRun(
        input=case.input,
        final_output=result.final_output,
        tool_calls=tool_calls,
        latency=latency,
        trace=cap.trace,
    )
