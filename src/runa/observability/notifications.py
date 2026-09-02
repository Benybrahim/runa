"""observability/notifications.py: a timeline view and a live notification bus.

Both are read-only surfaces over `Run.events` (manifesto §8) — nothing here
computes state the Run doesn't already have. `instrument()` wraps `run.emit`
on the instance so subscribers are notified as Events happen, without
`core/` needing to know observability exists.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from runa.core import Event, EventType, Run

Subscriber = Callable[[Event], None]

_SUMMARIES: dict[EventType, Callable[[dict[str, Any]], str]] = {
    EventType.RUN_QUEUED: lambda d: "run queued",
    EventType.RUN_STARTED: lambda d: "run started",
    EventType.RUN_PAUSED: lambda d: "run paused",
    EventType.RUN_RESUMED: lambda d: "run resumed",
    EventType.RUN_COMPLETED: lambda d: "run completed",
    EventType.RUN_FAILED: lambda d: f"run failed: {d.get('error', '')}",
    EventType.RUN_CANCELLED: lambda d: "run cancelled",
    EventType.APPROVAL_REQUIRED: (
        lambda d: f"approval required for tool call {d.get('tool_call_id', '')}"
    ),
    EventType.MODEL_CALLED: lambda d: "model called",
    EventType.MODEL_RESPONDED: lambda d: "model responded",
    EventType.TOOL_CALLED: lambda d: f"tool called: {d.get('tool', '')}",
    EventType.TOOL_COMPLETED: lambda d: f"tool completed: {d.get('tool', '')}",
    EventType.ARTIFACT_CREATED: (
        lambda d: f"artifact created: {d.get('artifact_id', '')}"
    ),
}


@dataclass
class TimelineEntry:
    timestamp: datetime
    type: EventType
    summary: str
    data: dict[str, Any]


def timeline(run: Run) -> list[TimelineEntry]:
    """A human-readable view of `run.events`, in order."""
    return [
        TimelineEntry(
            timestamp=event.timestamp,
            type=event.type,
            summary=_SUMMARIES.get(event.type, lambda d: event.type.value)(event.data),
            data=event.data,
        )
        for event in run.events
    ]


def instrument(run: Run, subscriber: Subscriber) -> Callable[[], None]:
    """Notify `subscriber` with each Event as `run` emits it.

    Returns a callable that removes the subscription. Multiple subscribers
    can be attached to the same run; each wraps the previous, so all are
    notified, in the order they were attached.
    """
    original_emit = run.emit

    def emit(event_type: EventType, **data: Any) -> Event:
        event = original_emit(event_type, **data)
        subscriber(event)
        return event

    run.emit = emit  # type: ignore[method-assign]

    def unsubscribe() -> None:
        run.emit = original_emit  # type: ignore[method-assign]

    return unsubscribe
