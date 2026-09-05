"""observability/webhook.py: ship each Event to an HTTP endpoint as it happens.

A `Subscriber`, the same protocol `instrument()` already notifies, that
POSTs a JSON payload per Event. External export is therefore an additional
subscriber, not a new subsystem: attach it with
`instrument(run, webhook("https://..."))` alongside, or instead of, any
other subscriber.

Sends synchronously on the calling thread by default, same as any other
subscriber `instrument()` drives. Pass a background `Queue` (e.g.
`runa.background.ThreadQueue`) to get the POST off the run's critical path.
"""

import json
from typing import Any
from urllib.request import Request, urlopen

from runa.background import InlineQueue, Queue
from runa.core import Event

from .notifications import Subscriber


def webhook(
    url: str,
    *,
    run_id: str | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 5.0,
    queue: Queue | None = None,
) -> Subscriber:
    """Build a Subscriber that POSTs each Event to `url` as JSON.

    Pass the `run_id` you're instrumenting, since `Event` itself doesn't
    carry one; it's the receiving end's only way to tell events from
    different runs apart.
    """
    queue = queue or InlineQueue()
    headers = {"Content-Type": "application/json", **(headers or {})}

    def send(event: Event) -> None:
        payload: dict[str, Any] = {
            "id": event.id,
            "type": event.type.value,
            "timestamp": event.timestamp.isoformat(),
            "data": event.data,
        }
        if run_id is not None:
            payload["run_id"] = run_id
        request = Request(
            url, data=json.dumps(payload).encode(), headers=headers, method="POST"
        )
        urlopen(request, timeout=timeout).close()

    def subscriber(event: Event) -> None:
        queue.enqueue(lambda: send(event))

    return subscriber
