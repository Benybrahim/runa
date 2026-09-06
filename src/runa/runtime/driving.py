"""DrivingGuard: exclusive in-process execution ownership for a Run.

Concurrency control over *who may advance a Run right now* is an Execution
concern (RUNA.md §1), not a fact about the Run itself: `Run` is meant to be
a plain, persistable record of what happened, and a `threading.Lock` can't
be meaningfully copied, compared, or serialized. This guard belongs to the
runtime layer instead, keyed by run id rather than by Run object identity,
and shared by every `Executor` in the process (a module-level default),
matching the guarantee the old `Run.begin_driving()`/`end_driving()` pair
used to provide: any two Executors racing to drive the same run id, not
just two calls on the same Executor instance, are caught.

This only catches this one framework entry point being called twice on the
same run id within one process, not two separate `Run` objects loaded for
the same persisted `run_id` in different processes: that hazard is a
`RunStore`/application concern (distributed locking), out of scope here.
See also `ThreadQueue`'s docstring, which already warns against reading a
queued Run from another thread, and `Conversation`'s docstring for the
analogous boundary there.
"""

import threading


class RunAlreadyDriving(Exception):
    """Raised when a second Executor tries to drive a Run already in flight.

    See `DrivingGuard.begin()`.
    """


class DrivingGuard:
    """Tracks which run ids are currently being driven, in this process."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._driving: set[str] = set()

    def begin(self, run_id: str) -> None:
        """Claim exclusive execution of `run_id`.

        Raises `RunAlreadyDriving` if another Executor is already driving
        this run id. Always release the claim with `end()`, in a `finally`,
        so the run id stays drivable again once the caller returns,
        including when it raised.
        """
        with self._lock:
            if run_id in self._driving:
                raise RunAlreadyDriving(
                    f"Run {run_id} is already being driven by another "
                    "Executor: two Executors cannot advance the same Run "
                    "concurrently"
                )
            self._driving.add(run_id)

    def end(self, run_id: str) -> None:
        """Release the claim `begin()` took."""
        with self._lock:
            self._driving.discard(run_id)


default_guard = DrivingGuard()
