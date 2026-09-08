"""`runa.tracing`: automatic hierarchical observability for `Agent.run`/`run_sync`.

The public surface is deliberately small: `Trace` and `Span` are the only two concepts, matching
`result.trace`. Nothing here needs to be called for tracing to happen — importing this package
(which `runa.agent` already does) registers `RunaTraceProcessor` against the OpenAI Agents SDK's
tracing, so every `Agent.run`/`run_sync` call is traced automatically. `trace`/`span` and
`observe` are the advanced, optional API described in the design.
"""

from agents.tracing import custom_span as span
from agents.tracing import trace

from runa.tracing._span import Span, SpanStatus, SpanType
from runa.tracing._trace import Trace
from runa.tracing.config import ConsoleExporter, SQLiteExporter, TraceExporter, observe
from runa.tracing.processor import RunaTraceProcessor, processor
from runa.tracing.storage import get_errors, get_recent_traces, get_trace, list_traces

__all__ = [
    "ConsoleExporter",
    "RunaTraceProcessor",
    "SQLiteExporter",
    "Span",
    "SpanStatus",
    "SpanType",
    "Trace",
    "TraceExporter",
    "get_errors",
    "get_recent_traces",
    "get_trace",
    "list_traces",
    "observe",
    "processor",
    "span",
    "trace",
]
