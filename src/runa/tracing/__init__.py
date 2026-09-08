"""`runa.tracing`: automatic hierarchical observability for `Agent.run`/`run_sync`.

The public surface is deliberately small: `Trace` and `Span` are the only two concepts, matching
`result.trace`. Nothing here needs to be called for tracing to happen — `runa._runner.Runner`
builds and exports a `Trace` for every run itself, with no separate registration step. `trace`/
`span` and `observe` are the advanced, optional API described in the design.
"""

from runa.tracing._manual import span, trace
from runa.tracing._span import Span, SpanStatus, SpanType
from runa.tracing._trace import Trace
from runa.tracing.config import ConsoleExporter, SQLiteExporter, TraceExporter, observe
from runa.tracing.storage import get_errors, get_recent_traces, get_trace, list_traces

__all__ = [
    "ConsoleExporter",
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
    "span",
    "trace",
]
