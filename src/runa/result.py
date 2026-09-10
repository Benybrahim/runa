"""result.py: `RunResult`/`RunResultStreaming`, what `Runner` returns to a caller."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from runa._types import RunContextWrapper, TResponseInputItem
from runa.lifecycle import RunHooks
from runa.run_config import RunConfig
from runa.run_state import Interruption, RunState
from runa.stream_events import StreamEvent
from runa.tracing.traces import Trace


@dataclass
class RunResult:
    """The outcome of one `Runner.run`/`run_sync` call."""

    final_output: Any
    context_wrapper: RunContextWrapper
    trace: Trace
    _original_input: list[TResponseInputItem]
    _generated_items: list[TResponseInputItem]
    interruptions: list[Interruption] = field(default_factory=list)
    _state: RunState | None = None
    input_guardrail_results: list[Any] = field(default_factory=list)
    output_guardrail_results: list[Any] = field(default_factory=list)
    tool_input_guardrail_results: list[Any] = field(default_factory=list)
    tool_output_guardrail_results: list[Any] = field(default_factory=list)

    def to_input_list(self) -> list[TResponseInputItem]:
        """Return `original_input + generated_items`: the full history after this run."""
        return [*self._original_input, *self._generated_items]

    def to_state(self) -> RunState:
        """Return the `RunState` to resolve `interruptions` against and resume with."""
        assert self._state is not None, "to_state() needs a run that actually paused"
        return self._state


class RunResultStreaming:
    """What `Runner.run_streamed` returns: an async iterator of `StreamEvent`s.

    `context_wrapper`/`to_input_list()` reflect the run's final state once the iterator has been
    fully consumed — both read the same `items` list and `RunContextWrapper` the streaming loop
    mutates in place as it goes, so there's no separate "final result" object to reconcile with.
    """

    def __init__(
        self,
        agent: Any,
        items: list[TResponseInputItem],
        context_wrapper: RunContextWrapper,
        run_config: RunConfig,
        hooks: RunHooks[Any],
    ) -> None:
        """Store the shared, mutable `items`/`context_wrapper` the streaming loop will update."""
        from runa.run_internal.streaming import _stream_async

        self._items = items
        self.context_wrapper = context_wrapper
        self._events = _stream_async(agent, items, context_wrapper, run_config, hooks)

    def __aiter__(self) -> AsyncIterator[StreamEvent]:
        """Iterate the `StreamEvent`s this run produces."""
        return self._events

    def to_input_list(self) -> list[TResponseInputItem]:
        """Return the full item list so far: original input plus everything generated."""
        return list(self._items)


__all__ = ["RunResult", "RunResultStreaming"]
