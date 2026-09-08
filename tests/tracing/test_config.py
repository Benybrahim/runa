"""Tests for `runa.tracing.observe`: the privacy/size policy and its `with`/bare-call forms."""

import agents.tracing as at

from runa.tracing import config, observe
from runa.tracing.processor import processor


def test_observe_bare_call_leaves_the_setting_applied() -> None:
    """A plain `observe(capture_inputs=False)` call (no `with`) applies immediately and sticks."""
    observe(capture_inputs=False)
    try:
        assert config.capture_inputs() is False
    finally:
        observe(capture_inputs=True)


def test_observe_context_manager_restores_the_previous_setting_on_exit() -> None:
    """`with observe(...):` restores whatever policy was active before it, once the block ends."""
    assert config.capture_inputs() is True

    with observe(capture_inputs=False):
        assert config.capture_inputs() is False

    assert config.capture_inputs() is True


def test_capture_inputs_false_means_span_input_is_not_recorded() -> None:
    """`observe(capture_inputs=False)` means a captured span's `input` stays `None`."""
    with (
        observe(capture_inputs=False),
        at.trace("T") as sdk_trace,
        at.function_span("now", input='{"x": 1}', output="ok"),
    ):
        pass
    trace = processor.pop_finished(sdk_trace.trace_id)

    assert trace is not None
    tool_span = next(span for span in trace.spans if span.type == "tool")
    assert tool_span.input is None
    assert tool_span.output == "ok"


def test_redact_scrubs_matching_keys_from_dict_shaped_input() -> None:
    """`redact=["email"]` replaces that key's value with `"[REDACTED]"` in dict-shaped input."""
    with (
        observe(redact=["email"]),
        at.trace("T") as sdk_trace,
        at.custom_span("lookup", data={"email": "a@b.com", "id": 1}),
    ):
        pass
    trace = processor.pop_finished(sdk_trace.trace_id)

    assert trace is not None
    span = trace.spans[0]
    assert span.input["email"] == "[REDACTED]"
    assert span.input["id"] == 1


def test_max_input_bytes_truncates_a_long_string_input() -> None:
    """`max_input_bytes` truncates a span's input once it exceeds the configured size."""
    with (
        observe(max_input_bytes=10),
        at.trace("T") as sdk_trace,
        at.function_span("now", input="x" * 100, output="ok"),
    ):
        pass
    trace = processor.pop_finished(sdk_trace.trace_id)

    assert trace is not None
    tool_span = next(span for span in trace.spans if span.type == "tool")
    assert len(tool_span.input) < 100
    assert tool_span.input.endswith("[truncated]")
