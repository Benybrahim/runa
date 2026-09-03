"""run_later() and the Queue protocol it dispatches through.

`run_later()` produces the same Run as running an Agent synchronously would
— only the executor differs (manifesto §13). Background execution is an
alternate transition through the same Run state machine, not a second
programming model.

`Queue` only promises that a job runs eventually; `DurableQueue` below adds
the ability to say *which run* is mid-flight, which is what lets a backend
like `SQLiteQueue` survive a process crash.
"""

from collections.abc import Callable
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from runa.core import Run
from runa.runtime import Executor

if TYPE_CHECKING:
    # Agent.run_later() calls this, so a runtime import here would cycle
    # back through agent.py — this is used for type hints only.
    from runa.agent import Agent


class Queue(Protocol):
    def enqueue(self, job: Callable[[], None]) -> None: ...


@runtime_checkable
class DurableQueue(Protocol):
    """A Queue that journals which run is in flight, so work orphaned by a
    crash can be found and resubmitted after a restart.

    A separate, optional protocol, not a second method tacked onto `Queue`
    — a Queue that only implements `enqueue()` still satisfies `Queue` on
    its own (`InlineQueue` and `ThreadQueue` included); one that also
    implements `enqueue_run()`/`pending()` additionally satisfies
    `DurableQueue`, structurally, with no base class to opt into.
    `run_later()` prefers `enqueue_run()` when a queue offers it, so the
    run being queued is recorded, not just the closure that runs it.
    """

    def enqueue_run(self, run_id: str, job: Callable[[], None]) -> None: ...
    def pending(self) -> list[str]: ...


class InlineQueue:
    """Default Queue: runs jobs immediately and synchronously.

    The development default — comparable to ActiveJob's :inline adapter.
    Real backends (a task queue, a worker process) are swapped in via
    configuration, not code changes.
    """

    def enqueue(self, job: Callable[[], None]) -> None:
        job()


def run_later(
    agent: "Agent", run: Run, executor: Executor, *, queue: Queue | None = None
) -> Run:
    """Queue a Run for background execution and return it immediately.

    With the default InlineQueue, the Run has already reached its next
    pause point (completion, failure, or an approval gate) by the time this
    returns. A real Queue defers that work elsewhere.
    """
    queue = queue or InlineQueue()
    run.queue()

    def job() -> None:
        executor.run(agent, run)

    if isinstance(queue, DurableQueue):
        queue.enqueue_run(run.id, job)
    else:
        queue.enqueue(job)
    return run
