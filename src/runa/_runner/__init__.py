"""`runa._runner`: `Runner`, Runa's own agent loop — replaces `agents.Runner`.

One turn: call the model, then either return its text (subject to output guardrails) or execute
whatever tools it called (subject to tool guardrails and `needs_approval`) and loop. A handoff is
just a tool call whose name matches a registered `Handoff`; calling it switches `current_agent` for
the rest of the run. Tracing spans (`runa.tracing.Span`/`Trace`) are emitted directly as the loop
runs — there is no separate SDK trace to adapt from, so this is the one and only tracer.

Split by concern: `_state` (config/result dataclasses, stream events), `_spans` (tracing span
helpers), `_helpers` (model/instruction/tool resolution), `_guardrails`, `_tool_calls`,
`_streaming`, and `_core` (the turn loop, run/resume orchestration, and `Runner` itself).
"""

from runa._runner._core import Runner
from runa._runner._helpers import _resolve_instructions as _resolve_instructions
from runa._runner._state import (
    AgentUpdatedStreamEvent,
    GuardrailResult,
    Interruption,
    RawResponsesStreamEvent,
    RunConfig,
    RunItemStreamEvent,
    RunResult,
    RunState,
    StreamEvent,
    gen_trace_id,
)
from runa._runner._streaming import RunResultStreaming

__all__ = [
    "AgentUpdatedStreamEvent",
    "GuardrailResult",
    "Interruption",
    "RawResponsesStreamEvent",
    "RunConfig",
    "RunItemStreamEvent",
    "RunResult",
    "RunResultStreaming",
    "RunState",
    "Runner",
    "StreamEvent",
    "gen_trace_id",
]
