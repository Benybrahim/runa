"""run_later() and the Queue protocol it dispatches through.

`run_later()` produces the same Run as running an Agent synchronously would
— only the executor differs (manifesto §13). Background execution is an
alternate transition through the same Run state machine, not a second
programming model.

`Queue` only promises that a job runs eventually; `DurableQueue` below adds
the ability to say *which run* is mid-flight, which is what lets a backend
like `SQLiteQueue` survive a process crash — and `recover_pending()` is the
automated version of the three-step manual recovery `SQLiteQueue` names in
its own docstring.
"""

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from runa.config import default_run_store
from runa.core import Run
from runa.persistence import RunStore
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

    Stamps `agent_name`/`agent_version` before queuing rather than leaving
    that to `Executor.run()`'s own seeding — a QUEUED Run is already durable
    state once a `DurableQueue` has journaled it, and architecture.md §14
    expects provenance to be attributable at that point, not only once
    execution actually starts.

    A `DurableQueue`'s journal only records *that* a run id is pending, not
    the Run itself (`background/sqlite.py` — an Agent/Executor hold live
    resources that don't survive a process boundary). So `recover_pending()`
    resolves an orphaned id against a `RunStore` — meaning this Run must be
    saved to `default_run_store()` before it's handed to the queue, or
    there's nothing for recovery to find after a crash. Saved before
    `queue.enqueue_run()`, not after, since a durable queue may start the
    job on another thread the moment it's called — saving first avoids
    racing that thread's own mutation of `run.events`/`run.messages`.

    The job also saves the Run back once it reaches its next pause point —
    the same thing `recover_pending()`'s own job wrapper does. Without this,
    the store would keep showing the Run as QUEUED forever after a normal
    (non-crash) completion: nothing else writes the terminal status back, so
    `runa runs show <id>` couldn't answer "what happened?" for durable
    background work, the one case durability is meant to cover.
    """
    queue = queue or InlineQueue()
    run.agent_name = agent.agent_name()
    run.agent_version = agent.version
    run.queue()

    durable = isinstance(queue, DurableQueue)

    def job() -> None:
        executor.run(agent, run)
        if durable:
            default_run_store().save(run)

    if durable:
        default_run_store().save(run)
        queue.enqueue_run(run.id, job)
    else:
        queue.enqueue(job)
    return run


def recover_pending(
    queue: DurableQueue,
    run_store: RunStore,
    executor: Executor,
    agents: Sequence[type["Agent"]],
) -> list[Run]:
    """Resubmit every Run a previous process left mid-flight.

    Call once at startup, right after constructing a `DurableQueue` from a
    path that might carry work orphaned by a crash. Automates the recovery
    `SQLiteQueue`'s own docstring describes as manual: `queue.pending()`
    names the orphaned run ids; each is looked up in `run_store` and
    matched to the `Agent` class that produced it via `Run.agent_name` (see
    `agents`, matched by `Agent.agent_name()`); matches are resubmitted
    through `queue.enqueue_run()` — the same path `run_later()` uses, so
    each resumes exactly where `Executor.run()` would resume any other
    paused Run. Unlike `run_later()`, each job also calls `run_store.save()`
    once it reaches its next pause point — recovery exists to make the
    store reflect what actually happened, so leaving that write to the
    caller would defeat the point (a second crash right after recovery
    would find the same stale row and repeat the whole recovery for no
    progress).

    A run id missing from `run_store` is skipped — it already finished and
    its journal row wasn't cleared for some unrelated reason. A Run whose
    `agent_name` isn't among `agents` is also skipped, since this call site
    has no Agent class to resume it with.

    Returns the Runs that were resubmitted.
    """
    by_name = {agent_cls.agent_name(): agent_cls for agent_cls in agents}
    recovered: list[Run] = []
    for run_id in queue.pending():
        run = run_store.get(run_id)
        if run is None:
            continue
        agent_cls = by_name.get(run.agent_name)
        if agent_cls is None:
            continue

        def job(run: Run = run, agent_cls: type["Agent"] = agent_cls) -> None:
            executor.run(agent_cls(), run)
            run_store.save(run)

        queue.enqueue_run(run.id, job)
        recovered.append(run)
    return recovered
