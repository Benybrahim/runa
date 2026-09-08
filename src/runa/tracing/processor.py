"""tracing/processor.py: `RunaTraceProcessor`, the adapter from the Agents SDK's own tracing.

The Agents SDK already wraps every `Runner.run()` call in a `Trace` and emits `agent`/
`generation`/`function` (tool)/`handoff`/`guardrail` spans as it executes (see
`agents/run.py`, `agents/run_internal/*.py`). Rather than instrumenting the agent loop a second
time, this module registers a `TracingProcessor` (`agents.tracing.TracingProcessor`) that listens
to those existing events and normalizes them into `runa.tracing`'s own `Trace`/`Span` — the
"Agents SDK trace -> Observability adapter -> Normalized Trace" pattern the design calls for.
"""

import logging
import threading
import time
from collections import OrderedDict
from datetime import datetime
from typing import Any

from agents.tracing import Span as SDKSpan
from agents.tracing import Trace as SDKTrace
from agents.tracing import TracingProcessor, add_trace_processor
from agents.tracing.span_data import (
    AgentSpanData,
    CustomSpanData,
    FunctionSpanData,
    GenerationSpanData,
    GuardrailSpanData,
    HandoffSpanData,
    ResponseSpanData,
    SpanData,
)

from runa.tracing import config
from runa.tracing._span import Span, SpanType
from runa.tracing._trace import Trace

logger = logging.getLogger("runa")

_TYPE_MAP: dict[str, SpanType] = {
    "agent": "agent",
    "function": "tool",
    "generation": "llm",
    "response": "llm",
    "handoff": "handoff",
    "guardrail": "guardrail",
    "custom": "custom",
}


def _parse_iso(value: str | None) -> float | None:
    if value is None:
        return None
    return datetime.fromisoformat(value).timestamp()


def _describe(data: SpanData) -> tuple[str, dict[str, Any], Any, Any, bool]:
    """Pull a `(name, attributes, input, output, triggered_error)` tuple out of typed `span_data`.

    Only fields the SDK actually populated are used — nothing here is fabricated.
    """
    if isinstance(data, AgentSpanData):
        attrs = {"handoffs": data.handoffs, "tools": data.tools, "output_type": data.output_type}
        return data.name, attrs, None, None, False
    if isinstance(data, FunctionSpanData):
        return data.name, {}, data.input, data.output, False
    if isinstance(data, GenerationSpanData):
        attrs: dict[str, Any] = {}
        if data.model:
            attrs["model"] = data.model
        if data.usage:
            attrs["usage"] = data.usage
        return data.model or "generation", attrs, data.input, data.output, False
    if isinstance(data, ResponseSpanData):
        attrs = {"usage": data.usage} if data.usage else {}
        return "response", attrs, data.input, None, False
    if isinstance(data, HandoffSpanData):
        name = f"{data.from_agent} -> {data.to_agent}"
        return name, {"from_agent": data.from_agent, "to_agent": data.to_agent}, None, None, False
    if isinstance(data, GuardrailSpanData):
        return data.name, {"triggered": data.triggered}, None, None, data.triggered
    if isinstance(data, CustomSpanData):
        return data.name, {}, data.data, None, False
    return data.type, {}, None, None, False


def _map_span(sdk_span: SDKSpan[Any]) -> Span | None:
    span_type = _TYPE_MAP.get(sdk_span.span_data.type)
    if span_type is None:
        return None

    name, attributes, raw_input, raw_output, triggered = _describe(sdk_span.span_data)
    error = sdk_span.error
    status = "error" if (error is not None or triggered) else "ok"

    max_output_bytes = config.tool_result_limit() if span_type == "tool" else config.output_limit()
    return Span(
        id=sdk_span.span_id,
        trace_id=sdk_span.trace_id,
        parent_id=sdk_span.parent_id,
        name=name,
        type=span_type,
        start_time=_parse_iso(sdk_span.started_at) or time.time(),
        end_time=_parse_iso(sdk_span.ended_at),
        status=status,
        attributes=attributes,
        input=config.apply_policy(raw_input, max_bytes=config.input_limit())
        if config.capture_inputs()
        else None,
        output=config.apply_policy(raw_output, max_bytes=max_output_bytes)
        if config.capture_outputs()
        else None,
        error=error["message"] if error else None,
    )


class RunaTraceProcessor(TracingProcessor):
    """Adapts the SDK's trace/span lifecycle into normalized `runa.tracing.Trace`/`Span` objects.

    Every finished trace is exported (SQLite by default, see `tracing/config.py`) fail-open —
    an exporter failure is logged, never raised, so tracing can never break an agent run. Finished
    traces are also kept in a small bounded `_finished` cache so `capture_trace`
    (`tracing/runner.py`) can hand one back to `Agent.run`/`run_agent_for_eval` synchronously,
    right after the `Runner.run()` call that produced it returns.
    """

    def __init__(self, max_finished: int = 512) -> None:
        """Initialize the empty active/finished trace state."""
        self._active: dict[str, list[Span]] = {}
        self._sdk_trace: dict[str, SDKTrace] = {}
        # SDK span id -> its SDK parent id, and the set of SDK span ids we dropped (span types
        # outside our controlled vocabulary, e.g. the SDK's internal "task"/"turn" bookkeeping
        # spans) — used to reparent a kept span's children past a dropped ancestor instead of
        # losing them from the tree. Both keyed by trace_id, cleared in `on_trace_end`.
        self._parent_of: dict[str, dict[str, str | None]] = {}
        self._dropped: dict[str, set[str]] = {}
        self._finished: OrderedDict[str, Trace] = OrderedDict()
        self._max_finished = max_finished
        self._lock = threading.Lock()

    def on_trace_start(self, trace: SDKTrace) -> None:
        """Start tracking spans for `trace.trace_id`."""
        with self._lock:
            self._active[trace.trace_id] = []
            self._sdk_trace[trace.trace_id] = trace
            self._parent_of[trace.trace_id] = {}
            self._dropped[trace.trace_id] = set()

    def on_trace_end(self, trace: SDKTrace) -> None:
        """Finalize the `Trace` for `trace.trace_id`, export it, and cache it for pickup."""
        with self._lock:
            spans = self._active.pop(trace.trace_id, [])
            self._sdk_trace.pop(trace.trace_id, None)
            self._parent_of.pop(trace.trace_id, None)
            self._dropped.pop(trace.trace_id, None)

        start_time = min((span.start_time for span in spans), default=time.time())
        trace_obj = Trace(
            id=trace.trace_id,
            name=trace.name,
            start_time=start_time,
            end_time=time.time(),
            spans=spans,
            metadata=dict(getattr(trace, "metadata", None) or {}),
        )

        for exporter in config.exporters():
            try:
                exporter.export(trace_obj)
            except Exception:
                logger.warning("tracing: exporter %r failed", exporter, exc_info=True)

        with self._lock:
            self._finished[trace.trace_id] = trace_obj
            while len(self._finished) > self._max_finished:
                self._finished.popitem(last=False)

    def on_span_start(self, span: SDKSpan[Any]) -> None:
        """Record `span`'s parentage, and whether it's a type we drop (see `_TYPE_MAP`).

        Spans are normalized and recorded once they finish, in `on_span_end`; this only tracks
        enough to reparent a kept span's children past a dropped ancestor.
        """
        with self._lock:
            self._parent_of.setdefault(span.trace_id, {})[span.span_id] = span.parent_id
            if _TYPE_MAP.get(span.span_data.type) is None:
                self._dropped.setdefault(span.trace_id, set()).add(span.span_id)

    def on_span_end(self, span: SDKSpan[Any]) -> None:
        """Normalize `span`, reparent it past any dropped ancestors, and record it."""
        mapped = _map_span(span)
        if mapped is None:
            return
        with self._lock:
            mapped.parent_id = self._resolve_parent(span.trace_id, mapped.parent_id)
            self._active.setdefault(span.trace_id, []).append(mapped)

    def _resolve_parent(self, trace_id: str, parent_id: str | None) -> str | None:
        """Walk `parent_id` up through any dropped spans to the nearest kept ancestor's id."""
        dropped = self._dropped.get(trace_id, set())
        parents = self._parent_of.get(trace_id, {})
        seen: set[str] = set()
        while parent_id is not None and parent_id in dropped and parent_id not in seen:
            seen.add(parent_id)
            parent_id = parents.get(parent_id)
        return parent_id

    def pop_finished(self, trace_id: str) -> Trace | None:
        """Remove and return the finished `Trace` for `trace_id`, if one is cached."""
        with self._lock:
            return self._finished.pop(trace_id, None)

    def snapshot(self, trace_id: str) -> Trace | None:
        """Build a `Trace` from whatever spans `trace_id` has accumulated so far, still open."""
        with self._lock:
            spans = list(self._active.get(trace_id, []))
            sdk_trace = self._sdk_trace.get(trace_id)
        if sdk_trace is None and not spans:
            return None
        start_time = min((span.start_time for span in spans), default=time.time())
        return Trace(
            id=trace_id,
            name=sdk_trace.name if sdk_trace is not None else trace_id,
            start_time=start_time,
            end_time=None,
            spans=spans,
            metadata=dict(getattr(sdk_trace, "metadata", None) or {}) if sdk_trace else {},
        )

    def shutdown(self) -> None:
        """Nothing to flush: traces are exported synchronously as they finish."""

    def force_flush(self) -> None:
        """Nothing to flush: traces are exported synchronously as they finish."""


processor = RunaTraceProcessor()
add_trace_processor(processor)


__all__ = ["RunaTraceProcessor", "processor"]
