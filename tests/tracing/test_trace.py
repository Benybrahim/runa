"""Tests for `runa.tracing.Trace`: `duration`, `status`, `errors`, and `__str__`."""

from runa.tracing import Span, Trace


def _span(id: str, parent_id: str | None, type: str = "custom", **kwargs: object) -> Span:
    return Span(
        id=id,
        trace_id="t1",
        parent_id=parent_id,
        name=id,
        type=type,  # type: ignore[arg-type]
        start_time=0.0,
        end_time=1.0,
        **kwargs,  # type: ignore[arg-type]
    )


def test_trace_duration_is_the_gap_between_start_and_end() -> None:
    """A finished trace's `duration` is `end_time - start_time`."""
    trace = Trace(id="t1", name="Agent", start_time=1.0, end_time=3.5)

    assert trace.duration == 2.5


def test_trace_duration_is_none_while_open() -> None:
    """A trace with no `end_time` yet has no `duration`."""
    trace = Trace(id="t1", name="Agent", start_time=1.0)

    assert trace.duration is None


def test_trace_status_is_error_if_any_span_errored() -> None:
    """`Trace.status` is `"error"` when at least one span errored, `"ok"` otherwise."""
    ok_trace = Trace(id="t1", name="Agent", start_time=0.0, end_time=1.0, spans=[_span("s1", None)])
    assert ok_trace.status == "ok"

    failing_span = _span("s2", None, status="error", error="boom")
    error_trace = Trace(id="t1", name="Agent", start_time=0.0, end_time=1.0, spans=[failing_span])
    assert error_trace.status == "error"


def test_trace_errors_lists_only_the_failing_spans() -> None:
    """`Trace.errors` returns just the spans whose `status` is `"error"`."""
    ok_span = _span("s1", None)
    failing_span = _span("s2", None, status="error", error="boom")
    trace = Trace(
        id="t1", name="Agent", start_time=0.0, end_time=1.0, spans=[ok_span, failing_span]
    )

    assert trace.errors == [failing_span]


def test_trace_str_renders_an_empty_trace_as_just_the_header() -> None:
    """A trace with no spans still renders a header line."""
    trace = Trace(id="t1", name="Agent", start_time=0.0, end_time=1.0)

    assert str(trace) == "Trace Agent [1.00s] ✓"


def test_trace_str_renders_nested_spans_as_a_tree() -> None:
    """`__str__` nests spans under their `parent_id`, labeling each by its `type`."""
    agent = _span("agent1", None, type="agent")
    llm = _span("llm1", "agent1", type="llm")
    tool = _span("tool1", "agent1", type="tool")
    trace = Trace(
        id="t1", name="SupportAgent", start_time=0.0, end_time=1.0, spans=[agent, llm, tool]
    )

    rendered = str(trace)

    assert rendered.startswith("Trace SupportAgent [1.00s] ✓")
    assert "Agent agent1" in rendered
    assert "LLM llm1" in rendered
    assert "Tool tool1" in rendered
    # both llm1 and tool1 are indented under agent1, not at the root
    lines = rendered.splitlines()
    agent_line_index = next(i for i, line in enumerate(lines) if "Agent agent1" in line)
    for name in ("LLM llm1", "Tool tool1"):
        index, line = next((i, line) for i, line in enumerate(lines) if name in line)
        assert index > agent_line_index
        assert line.strip() != line  # indented, not flush left


def test_trace_str_shows_error_glyph_and_message_for_a_failing_span() -> None:
    """A failing span renders with the `✗` glyph and its error message."""
    failing = _span("boom1", None, status="error", error="tool exploded")
    trace = Trace(id="t1", name="Agent", start_time=0.0, end_time=1.0, spans=[failing])

    rendered = str(trace)

    assert "✗" in rendered
    assert "tool exploded" in rendered
