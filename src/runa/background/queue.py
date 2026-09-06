"""run_later() and the Queue protocol it dispatches through.

`run_later()` produces the same Run as running an Agent would; only the
Executor differs (manifesto §13). Background execution is an alternate
transition through the same Run state machine, not a second programming
model. `Executor.run()` is a coroutine, but each job here is a plain
synchronous callable (the `Queue` protocol's shape): `asyncio.run()` drives
it to completion on whatever thread the Queue calls `job()` from, a fresh
event loop each time, exactly like `Agent.run_sync()`.

`Queue` only promises that a job runs eventually; `DurableQueue` below adds
the ability to say *which run* is mid-flight, which is what lets a backend
like `SQLiteQueue` survive a process crash, and `recover_pending()` is the
automated version of the three-step manual recovery `SQLiteQueue` names in
its own docstring.
"""

import asyncio
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from runa.application import application
from runa.core import Conversation, Run
from runa.persistence import ConversationStore, RunStore
from runa.runtime import Executor

if TYPE_CHECKING:
    # Agent.run_later() calls this, so a runtime import here would cycle
    # back through agent.py; this is used for type hints only.
    from runa.agent import Agent


class Queue(Protocol):
    def enqueue(self, job: Callable[[], None]) -> None: ...


@runtime_checkable
class DurableQueue(Protocol):
    """A Queue that journals which run is in flight, so work orphaned by a
    crash can be found and resubmitted after a restart.

    A separate, optional protocol, not a second method tacked onto `Queue`:
    a Queue that only implements `enqueue()` still satisfies `Queue` on
    its own (`InlineQueue` and `ThreadQueue` included); one that also
    implements `enqueue_run()`/`pending()`/`forget()` additionally satisfies
    `DurableQueue`, structurally, with no base class to opt into.
    `run_later()` prefers `enqueue_run()` when a queue offers it, so the
    run being queued is recorded, not just the closure that runs it.
    """

    def enqueue_run(self, run_id: str, job: Callable[[], None]) -> None: ...
    def pending(self) -> list[str]: ...

    def forget(self, run_id: str) -> None:
        """Clear `run_id` from the pending journal without running a job for it.

        `enqueue_run()`'s job clears its own row once it runs; this is for
        the other case, `recover_pending()` deciding a pending run id should
        *not* be resubmitted at all (see its own docstring). Without this,
        that run id would keep showing up in `pending()` on every future
        startup, and (once `recover_pending()` marks the Run FAILED for the
        same reason each time) `run.fail()` would raise `IllegalTransition`
        on the second attempt, since a FAILED Run can't fail again.
        """
        ...


class InlineQueue:
    """Default Queue: runs jobs immediately and synchronously.

    The development default, comparable to ActiveJob's :inline adapter.
    Real backends (a task queue, a worker process) are swapped in via
    configuration, not code changes.
    """

    def enqueue(self, job: Callable[[], None]) -> None:
        job()


def run_later(
    agent: "Agent",
    run: Run,
    executor: Executor,
    *,
    queue: Queue | None = None,
    conversation: Conversation | None = None,
) -> Run:
    """Queue a Run for background execution and return it immediately.

    With the default InlineQueue, the Run has already reached its next
    pause point (completion, failure, or an approval gate) by the time this
    returns. A real Queue defers that work elsewhere.

    Stamps `agent_name`/`agent_version` before queuing rather than leaving
    that to `Executor.run()`'s own seeding: a QUEUED Run is already durable
    state once a `DurableQueue` has journaled it, and architecture.md §14
    expects provenance to be attributable at that point, not only once
    execution actually starts. `run.conversation_id` is already set by the
    caller (`Agent.run_later()`) at Run construction time, for the same
    reason. The live `conversation`, however, is a call-time collaborator
    that can't survive a process boundary the way an id can (see
    `recover_pending()`): it's threaded straight into the job's own
    `executor.run()` call, not persisted.

    A `DurableQueue`'s journal only records *that* a run id is pending, not
    the Run itself (`background/sqlite.py`: an Agent/Executor hold live
    resources that don't survive a process boundary). So `recover_pending()`
    resolves an orphaned id against a `RunStore`, meaning this Run must be
    saved to `application.run_store` before it's handed to the queue, or
    there's nothing for recovery to find after a crash. Saved before
    `queue.enqueue_run()`, not after, since a durable queue may start the
    job on another thread the moment it's called, so saving first avoids
    racing that thread's own mutation of `run.events`/`run.messages`.

    The job also saves the Run back once it reaches its next pause point,
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
        asyncio.run(executor.run(agent, run, conversation=conversation))
        if durable:
            application.run_store.save(run)

    if durable:
        application.run_store.save(run)
        queue.enqueue_run(run.id, job)
    else:
        queue.enqueue(job)
    return run


def recover_pending(
    queue: DurableQueue,
    run_store: RunStore,
    executor: Executor,
    agents: Sequence[type["Agent"]],
    *,
    conversation_store: ConversationStore | None = None,
) -> list[Run]:
    """Resubmit every Run a previous process left mid-flight.

    Call once at startup, right after constructing a `DurableQueue` from a
    path that might carry work orphaned by a crash. Automates the recovery
    `SQLiteQueue`'s own docstring describes as manual: `queue.pending()`
    names the orphaned run ids; each is looked up in `run_store` and
    matched to the `Agent` class that produced it via `Run.agent_name` (see
    `agents`, matched by `Agent.agent_name()`); matches are resubmitted
    through `queue.enqueue_run()`, the same path `run_later()` uses. Unlike
    `run_later()`, each job also calls `run_store.save()` once it reaches
    its next pause point; recovery exists to make the store reflect what
    actually happened, so leaving that write to the caller would defeat the
    point (a second crash right after recovery would find the same stale
    row and repeat the whole recovery for no progress).

    IMPORTANT: this restarts the Run, it does not resume it mid-flight.
    `run_later()` only ever persists the Run's *pre-dispatch* snapshot
    (QUEUED, no messages, no tool calls yet); nothing checkpoints progress
    while a Run is actually executing. So `run` here is that same
    pre-dispatch snapshot, regardless of how far the crashed process
    actually got: `Executor.run()` sees a fresh QUEUED Run and seeds and
    runs it from the beginning, calling the model and any tools again from
    scratch. Any tool call the crashed process already completed (a real
    charge, a real email, a real ticket) is repeated. Building true
    mid-execution checkpointing would need to resolve a harder problem
    first: `ToolCall.attempts` is incremented before a call runs (see
    `Executor._call_tool`), so a crash between that increment and the call
    returning would otherwise look like a *completed* call on resume
    (`ToolCall.completed` only checks `attempts > 0 and error is None`) and
    get silently skipped rather than retried or flagged, the same
    attempted-vs-observed-effect ambiguity `EffectStatus.UNKNOWN` already
    models for a single retried call (architecture.md §13), not yet
    resolved at the level of a whole recovered Run. Only give `agents` to
    `recover_pending()` whose tools are safe to run again in full:
    `Tool.idempotent` is the existing signal for exactly this.

    A recovered Run's `conversation_id` survives (it's part of the Run
    snapshot in `run_store`), but the live `Conversation` object does not:
    it never crossed the process boundary in the first place. Pass
    `conversation_store` (the same explicit-dependency pattern `run_store`/
    `executor`/`agents` already use here) to resolve it back: a Run with a
    `conversation_id` is only resubmitted once `conversation_store.get(...)`
    returns the matching `Conversation`, resolved synchronously in this loop
    before the job is ever queued, exactly like `agent_name` is matched to
    an `Agent` class above. A Run with a `conversation_id` that can't be
    resolved this way (no `conversation_store` given, or the Conversation
    isn't in it) is never queued and never executed with a silently
    different context: it's instead failed explicitly, with `run.error`
    naming the unresolved id, and forgotten from `queue`'s journal so it
    isn't rediscovered as pending and re-failed (which would raise
    `IllegalTransition`, a FAILED Run can't fail twice) on the next startup.
    A Run with no `conversation_id` is unaffected and recovers exactly as
    before, `conversation_store` or not.

    A run id missing from `run_store` is skipped: it already finished and
    its journal row wasn't cleared for some unrelated reason. A Run whose
    `agent_name` isn't among `agents` is also skipped, since this call site
    has no Agent class to resume it with. An already-terminal Run loaded
    from `run_store` (e.g. from a crash timed exactly between a previous
    recovery attempt saving it and forgetting its journal row) is skipped
    the same way, rather than re-processed.

    Returns the Runs this call took action on: resubmitted for execution,
    or (for an unresolved Conversation) already failed and persisted.
    """
    by_name = {agent_cls.agent_name(): agent_cls for agent_cls in agents}
    recovered: list[Run] = []
    for run_id in queue.pending():
        run = run_store.get(run_id)
        if run is None:
            continue
        if run.is_terminal:
            continue
        if run.agent_name is None:
            continue
        agent_cls = by_name.get(run.agent_name)
        if agent_cls is None:
            continue

        conversation: Conversation | None = None
        if run.conversation_id is not None:
            conversation = (
                conversation_store.get(run.conversation_id)
                if conversation_store is not None
                else None
            )
            if conversation is None:
                # QUEUED can't transition straight to FAILED (only RUNNING
                # can); start() first, the same way Executor.run() itself
                # moves a Run to RUNNING before a seeding bug can fail it,
                # so recovery failing here looks like any other failure a
                # Run can have, not a special case in the status machine.
                run.start()
                run.fail(
                    error=(
                        f"cannot recover: Conversation {run.conversation_id!r} "
                        "could not be resolved (no conversation_store given "
                        "to recover_pending(), or it was not found in it)"
                    )
                )
                # Save the failure first: run_store is the source of truth
                # for what happened, so if a crash lands between these two
                # calls, losing the journal-cleanup (a merely inert stale
                # pending() entry, caught by the is_terminal check above on
                # the next attempt) is preferable to losing the failure
                # itself (which would silently read back as QUEUED forever).
                run_store.save(run)
                queue.forget(run.id)
                recovered.append(run)
                continue

        def job(
            run: Run = run,
            agent_cls: type["Agent"] = agent_cls,
            conversation: Conversation | None = conversation,
        ) -> None:
            asyncio.run(executor.run(agent_cls(), run, conversation=conversation))
            run_store.save(run)

        queue.enqueue_run(run.id, job)
        recovered.append(run)
    return recovered
