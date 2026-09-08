"""Tests for `runa.tracing.Span`."""

from runa.tracing import Span


def test_span_duration_is_none_while_open() -> None:
    """A span with no `end_time` yet has no `duration`."""
    span = Span(id="s1", trace_id="t1", parent_id=None, name="agent", type="agent", start_time=1.0)

    assert span.duration is None


def test_span_duration_is_the_gap_between_start_and_end() -> None:
    """A finished span's `duration` is `end_time - start_time`."""
    span = Span(
        id="s1",
        trace_id="t1",
        parent_id=None,
        name="agent",
        type="agent",
        start_time=1.0,
        end_time=1.5,
    )

    assert span.duration == 0.5


def test_span_defaults_to_ok_with_no_input_output_or_error() -> None:
    """A freshly built span defaults to `status="ok"` and no captured data."""
    span = Span(id="s1", trace_id="t1", parent_id=None, name="agent", type="agent", start_time=1.0)

    assert span.status == "ok"
    assert span.input is None
    assert span.output is None
    assert span.error is None
    assert span.attributes == {}
