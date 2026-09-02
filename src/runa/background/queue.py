"""run_later() and the Queue protocol it dispatches through.

`run_later()` produces the same Run as running an Agent synchronously would
— only the executor differs (manifesto §13). Background execution is an
alternate transition through the same Run state machine, not a second
programming model.
"""

from collections.abc import Callable
from typing import Protocol

from runa.agent import Agent
from runa.core import Run
from runa.runtime import Executor


class Queue(Protocol):
    def enqueue(self, job: Callable[[], None]) -> None: ...


class InlineQueue:
    """Default Queue: runs jobs immediately and synchronously.

    The development default — comparable to ActiveJob's :inline adapter.
    Real backends (a task queue, a worker process) are swapped in via
    configuration, not code changes.
    """

    def enqueue(self, job: Callable[[], None]) -> None:
        job()


def run_later(
    agent: Agent, run: Run, executor: Executor, *, queue: Queue | None = None
) -> Run:
    """Queue a Run for background execution and return it immediately.

    With the default InlineQueue, the Run has already reached its next
    pause point (completion, failure, or an approval gate) by the time this
    returns. A real Queue defers that work elsewhere.
    """
    queue = queue or InlineQueue()
    run.queue()
    queue.enqueue(lambda: executor.run(agent, run))
    return run
