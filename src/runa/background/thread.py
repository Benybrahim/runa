"""ThreadQueue: runs enqueued jobs on a background thread pool.

Same `Queue` protocol as `InlineQueue` — swapping one for the other at
`run_later(queue=...)` is a one-line change, not a code change. Unlike
`InlineQueue`, `enqueue()` returns before the job has run: the `Run` it's
driving is left `QUEUED`, not yet at its next pause point. `Run` isn't
synchronized against a background writer, so once a job is enqueued, look
the `Run` up again later (e.g. via a `RunStore`) rather than keep reading
the same object from another thread.
"""

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor


class ThreadQueue:
    """Queue backed by a bounded thread pool."""

    def __init__(self, max_workers: int = 4) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max_workers)

    def enqueue(self, job: Callable[[], None]) -> None:
        self._executor.submit(job)

    def close(self, *, wait: bool = True) -> None:
        """Stop accepting new jobs; `wait=True` blocks until running jobs finish."""
        self._executor.shutdown(wait=wait)
