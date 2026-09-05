"""SQLiteQueue: a Queue that survives a process crash.

`ThreadQueue` keeps enqueued jobs only in the thread pool's own in-memory
queue: if the process dies mid-job, that job (and anything still waiting
behind it) is gone, and nothing records it was ever there. SQLiteQueue
additionally journals each job's `run_id` to a SQLite table before
submitting it to the thread pool, clearing the row once the job finishes.

It can't persist the job closure itself: an Agent and Executor hold live
resources (model clients, API keys) that don't survive a process boundary,
so recovery after a crash isn't automatic. On restart, call `pending()`
to find run ids a previous process left mid-flight, look each one up in a
RunStore, and resubmit it with `enqueue_run()`.
"""

import sqlite3
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

_SCHEMA = """
CREATE TABLE IF NOT EXISTS pending_jobs (
    run_id TEXT PRIMARY KEY
)
"""


class SQLiteQueue:
    """Queue backed by a bounded thread pool, journaled to SQLite at `path`.

    Same protocol as `ThreadQueue`: swapping one for the other at
    `run_later(queue=...)` is a one-line change, plus `DurableQueue`'s
    `enqueue_run()`/`pending()`, which `run_later()` uses automatically.
    """

    def __init__(self, path: str, max_workers: int = 4) -> None:
        self._connection = sqlite3.connect(path, check_same_thread=False)
        # check_same_thread=False only lifts sqlite3's same-thread check; it
        # does not make one Connection object safe to call from multiple
        # threads at once (the sqlite3 docs say as much). Every job here
        # runs on a ThreadPoolExecutor worker and clears its own journal row
        # in `wrapped()` below, concurrently with `enqueue_run()`/`pending()`
        # on whatever thread calls those, so every access is serialized
        # through `self._lock`.
        self._lock = threading.Lock()
        with self._lock:
            self._connection.execute(_SCHEMA)
            self._connection.commit()
        self._executor = ThreadPoolExecutor(max_workers=max_workers)

    def enqueue(self, job: Callable[[], None]) -> None:
        self._executor.submit(job)

    def enqueue_run(self, run_id: str, job: Callable[[], None]) -> None:
        with self._lock:
            self._connection.execute(
                "INSERT OR REPLACE INTO pending_jobs (run_id) VALUES (?)", (run_id,)
            )
            self._connection.commit()

        def wrapped() -> None:
            try:
                job()
            finally:
                with self._lock:
                    self._connection.execute(
                        "DELETE FROM pending_jobs WHERE run_id = ?", (run_id,)
                    )
                    self._connection.commit()

        self._executor.submit(wrapped)

    def pending(self) -> list[str]:
        """Run ids left mid-flight by a previous process (crashed before its
        job finished). Resolve each one against a RunStore and resubmit via
        `enqueue_run()` to recover it.
        """
        with self._lock:
            rows = self._connection.execute(
                "SELECT run_id FROM pending_jobs"
            ).fetchall()
        return [row[0] for row in rows]

    def close(self, *, wait: bool = True) -> None:
        """Stop accepting new jobs; `wait=True` blocks until running jobs
        finish.

        Same `SIGTERM` caveat as `ThreadQueue.close()`: a normal process
        exit already waits without calling this, but `SIGTERM` kills a
        worker thread mid-job with no cleanup unless the application calls
        this from its own signal handler (see docs/guides.md, "Shutting
        Down a Background Queue"). `recover_pending()` is what makes that
        survivable regardless: the journal row this job's `wrapped()`
        never got to clear is exactly what it looks for on next startup.
        """
        self._executor.shutdown(wait=wait)
        with self._lock:
            self._connection.close()
