from runa.agent import Agent
from runa.background import InlineQueue, recover_pending, run_later
from runa.core import Message, Role, Run, RunStatus
from runa.persistence import InMemoryRunStore
from runa.runtime import Executor
from tests.fakes import FakeProvider


class GreeterAgent(Agent):
    instructions = "Say hello."


class FarewellAgent(Agent):
    instructions = "Say goodbye."


class FakeDurableQueue:
    """A DurableQueue whose `pending()` is scripted, for recover_pending tests.

    `enqueue_run()` runs the job immediately, like InlineQueue — recovery
    tests only need to see the resumed Run's end state, not a real
    background thread.
    """

    def __init__(self, pending_ids: list[str]) -> None:
        self._pending_ids = pending_ids
        self.enqueued: list[str] = []

    def enqueue(self, job):
        job()

    def enqueue_run(self, run_id, job):
        self.enqueued.append(run_id)
        job()

    def pending(self) -> list[str]:
        return self._pending_ids


def test_run_later_with_inline_queue_runs_synchronously_to_completion():
    provider = FakeProvider(responses=[Message(role=Role.ASSISTANT, content="hi")])
    executor = Executor(provider)
    agent = GreeterAgent()
    run = Run(input="hello")

    result = run_later(agent, run, executor)

    assert result is run
    assert result.status == RunStatus.COMPLETED
    assert result.result == "hi"


def test_run_later_queues_before_a_custom_queue_dispatches():
    seen_status = []

    class RecordingQueue:
        def enqueue(self, job):
            seen_status.append(run.status)
            job()

    provider = FakeProvider(responses=[Message(role=Role.ASSISTANT, content="hi")])
    executor = Executor(provider)
    agent = GreeterAgent()
    run = Run(input="hello")

    run_later(agent, run, executor, queue=RecordingQueue())

    assert seen_status == [RunStatus.QUEUED]
    assert run.status == RunStatus.COMPLETED


def test_deferred_queue_leaves_the_run_queued_until_dispatched():
    jobs = []

    class DeferredQueue:
        def enqueue(self, job):
            jobs.append(job)

    provider = FakeProvider(responses=[Message(role=Role.ASSISTANT, content="hi")])
    executor = Executor(provider)
    agent = GreeterAgent()
    run = Run(input="hello")

    run_later(agent, run, executor, queue=DeferredQueue())

    assert run.status == RunStatus.QUEUED
    jobs[0]()
    assert run.status == RunStatus.COMPLETED


def test_inline_queue_runs_the_job_immediately():
    calls = []
    InlineQueue().enqueue(lambda: calls.append("ran"))

    assert calls == ["ran"]


def _queued_run(*, agent_name: str) -> Run:
    """A Run left QUEUED, as if a process crashed right after journaling it."""
    run = Run(input="hello", agent_name=agent_name)
    run.queue()
    return run


def test_recover_pending_resumes_a_run_left_mid_flight():
    run_store = InMemoryRunStore()
    orphaned = _queued_run(agent_name="GreeterAgent")
    run_store.save(orphaned)
    queue = FakeDurableQueue(pending_ids=[orphaned.id])
    provider = FakeProvider(responses=[Message(role=Role.ASSISTANT, content="hi")])
    executor = Executor(provider)

    recovered = recover_pending(queue, run_store, executor, agents=[GreeterAgent])

    assert recovered == [orphaned]
    assert queue.enqueued == [orphaned.id]
    assert orphaned.status == RunStatus.COMPLETED
    assert orphaned.result == "hi"


def test_recover_pending_skips_a_run_id_missing_from_the_store():
    run_store = InMemoryRunStore()
    queue = FakeDurableQueue(pending_ids=["ghost-run"])
    executor = Executor(FakeProvider(responses=[]))

    recovered = recover_pending(queue, run_store, executor, agents=[GreeterAgent])

    assert recovered == []
    assert queue.enqueued == []


def test_recover_pending_skips_a_run_whose_agent_is_not_in_the_list():
    run_store = InMemoryRunStore()
    orphaned = _queued_run(agent_name="GreeterAgent")
    run_store.save(orphaned)
    queue = FakeDurableQueue(pending_ids=[orphaned.id])
    executor = Executor(FakeProvider(responses=[]))

    # only FarewellAgent is known here, not the GreeterAgent that produced it
    recovered = recover_pending(queue, run_store, executor, agents=[FarewellAgent])

    assert recovered == []
    assert queue.enqueued == []
    assert orphaned.status == RunStatus.QUEUED  # untouched, not resumed


def test_recover_pending_matches_each_run_to_its_own_agent_class():
    run_store = InMemoryRunStore()
    greeting = _queued_run(agent_name="GreeterAgent")
    farewell = _queued_run(agent_name="FarewellAgent")
    run_store.save(greeting)
    run_store.save(farewell)
    queue = FakeDurableQueue(pending_ids=[greeting.id, farewell.id])
    provider = FakeProvider(
        responses=[
            Message(role=Role.ASSISTANT, content="hi"),
            Message(role=Role.ASSISTANT, content="bye"),
        ]
    )
    executor = Executor(provider)

    recovered = recover_pending(
        queue, run_store, executor, agents=[GreeterAgent, FarewellAgent]
    )

    assert {run.id for run in recovered} == {greeting.id, farewell.id}
    assert greeting.result == "hi"
    assert farewell.result == "bye"
