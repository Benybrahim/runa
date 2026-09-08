"""tracing/runner.py: `capture_trace`, the shared "run through `Runner.run()`, get a `Trace`" glue.

Both `Agent.run`/`run_sync` (`runa/agent.py`) and `run_agent_for_eval`
(`runa/eval/tracing/adapter.py`) need the same thing: fold a trace id into the `RunConfig` passed
to `Runner.run()`/`Runner.run_sync()`, then collect the resulting `Trace` once it returns. Sharing
this one mechanism (not just the `Trace` dataclass shape) is what makes eval and observability
genuinely consume the same trace representation instead of two parallel ones.
"""

import time
from typing import Any

from agents.tracing import gen_trace_id, get_current_trace

from runa.tracing._trace import Trace
from runa.tracing.processor import processor


class capture_trace:
    """Fold a trace id into a `RunConfig` and collect the `Trace` `Runner.run()` produced.

    Usage::

        with capture_trace(workflow_name=..., group_id=...) as capture:
            fields = capture.run_config_fields
            result = await Runner.run(..., run_config=replace(_RUN_CONFIG, **fields))
        trace = capture.trace

    When no trace is already active, `Runner.run()` creates a brand-new one using the `trace_id`
    generated here and finishes it before returning, so `capture.trace` is a complete tree. When
    this is called from inside an explicit outer `with runa.tracing.trace(...):` block (advanced
    usage), `Runner.run()` reuses that outer trace instead — it won't be finished yet when this
    call returns, so `capture.trace` is instead a snapshot of the spans produced so far.
    """

    def __init__(
        self,
        *,
        workflow_name: str,
        group_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Store the trace naming to use if a new trace ends up being created."""
        self._workflow_name = workflow_name
        self._group_id = group_id
        self._metadata = metadata
        self.trace: Trace
        self.trace_id: str
        self.run_config_fields: dict[str, Any]
        self._nested = False

    def __enter__(self) -> capture_trace:
        """Resolve the trace id to use and the `RunConfig` fields that select it."""
        outer = get_current_trace()
        self._nested = outer is not None
        self.trace_id = outer.trace_id if outer is not None else gen_trace_id()
        self.run_config_fields = {
            "trace_id": self.trace_id,
            "workflow_name": self._workflow_name,
            "group_id": self._group_id,
            "trace_metadata": self._metadata,
        }
        return self

    def __exit__(self, *exc_info: object) -> None:
        """Collect the finished (or, if nested, in-progress) `Trace` for this call."""
        collected = (
            processor.snapshot(self.trace_id)
            if self._nested
            else processor.pop_finished(self.trace_id)
        )
        now = time.time()
        self.trace = collected or Trace(
            id=self.trace_id,
            name=self._workflow_name,
            start_time=now,
            end_time=now,
            spans=[],
            metadata=self._metadata or {},
        )


__all__ = ["capture_trace"]
