"""Tests for `runa.tracing.processor.RunaTraceProcessor`, the adapter off the SDK's own tracing.

Drives the Agents SDK's own `agents.tracing` primitives directly (`trace()`, `agent_span()`, ...)
rather than a full `Runner.run()` call — the fastest way to test the mapping/reparenting logic in
isolation, per the design's own "use the SDK's existing tracing hooks" approach.
"""

import agents.tracing as at

from runa.tracing.processor import processor


def test_processor_maps_agent_llm_and_tool_spans() -> None:
    """`agent`/`generation`/`function` SDK spans map to our `"agent"`/`"llm"`/`"tool"` types."""
    with at.trace("TestAgent") as sdk_trace, at.agent_span("TestAgent", tools=["now"]):
        with at.function_span("now", input="{}", output="2024"):
            pass
        with at.generation_span(model="gpt-5", usage={"input_tokens": 10, "output_tokens": 5}):
            pass

    trace = processor.pop_finished(sdk_trace.trace_id)

    assert trace is not None
    types_by_name = {span.name: span.type for span in trace.spans}
    assert types_by_name["TestAgent"] == "agent"
    assert types_by_name["now"] == "tool"
    assert types_by_name["gpt-5"] == "llm"


def test_processor_reparents_children_past_dropped_task_and_turn_spans() -> None:
    """The SDK's internal `task`/`turn` bookkeeping spans are dropped, not left as orphans."""
    with (
        at.trace("TestAgent") as sdk_trace,
        at.agent_span("TestAgent"),
        at.task_span("run"),
        at.turn_span(0, "TestAgent"),
        at.function_span("now", input="{}", output="ok"),
    ):
        pass

    trace = processor.pop_finished(sdk_trace.trace_id)

    assert trace is not None
    assert {span.name for span in trace.spans} == {"TestAgent", "now"}
    agent = next(span for span in trace.spans if span.name == "TestAgent")
    tool = next(span for span in trace.spans if span.name == "now")
    assert tool.parent_id == agent.id


def test_processor_marks_a_triggered_guardrail_as_an_error_span() -> None:
    """A guardrail span whose `triggered` flag is set is recorded with `status="error"`."""
    with at.trace("TestAgent") as sdk_trace, at.guardrail_span("block_empty") as span:
        span.span_data.triggered = True

    trace = processor.pop_finished(sdk_trace.trace_id)

    assert trace is not None
    guardrail_span = next(span for span in trace.spans if span.type == "guardrail")
    assert guardrail_span.status == "error"


def test_processor_drops_span_types_outside_the_controlled_vocabulary() -> None:
    """A span type with no entry in the controlled vocabulary (e.g. `mcp_tools`) isn't recorded."""
    with at.trace("TestAgent") as sdk_trace, at.mcp_tools_span(server="fs", result=["read"]):
        pass

    trace = processor.pop_finished(sdk_trace.trace_id)

    assert trace is not None
    assert trace.spans == []


def test_processor_snapshot_reflects_spans_before_the_trace_finishes() -> None:
    """`snapshot()` returns spans recorded so far for a trace that hasn't ended yet."""
    with at.trace("Outer") as sdk_trace:
        with at.agent_span("Outer"):
            pass
        snapshot = processor.snapshot(sdk_trace.trace_id)

    assert snapshot is not None
    assert snapshot.end_time is None
    assert any(span.name == "Outer" for span in snapshot.spans)
