from runa.agent import Agent
from runa.application import application
from runa.background import InlineQueue, recover_pending, run_later
from runa.core import Conversation, Message, Role, Run, RunStatus
from runa.persistence import InMemoryConversationStore, InMemoryRunStore
from runa.runtime import Executor
from tests.fakes import FakeProvider


class GreeterAgent(Agent):
    instructions = "Say hello."


class FarewellAgent(Agent):
    instructions = "Say goodbye."


class FakeDurableQueue:
    """A DurableQueue whose `pending()` is scripted, for recover_pending tests.

    `enqueue_run()` runs the job immediately, like InlineQueue; recovery
    tests only need to see the resumed Run's end state, not a real
    background thread.
    """

    def __init__(self, pending_ids: list[str]) -> None:
        self._pending_ids = pending_ids
        self.enqueued: list[str] = []
        self.forgotten: list[str] = []

    def enqueue(self, job):
        job()

    def enqueue_run(self, run_id, job):
        self.enqueued.append(run_id)
        job()

    def pending(self) -> list[str]:
        return [rid for rid in self._pending_ids if rid not in self.forgotten]

    def forget(self, run_id: str) -> None:
        self.forgotten.append(run_id)


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


def test_run_later_stamps_agent_provenance_before_the_job_runs():
    class DeferredQueue:
        def __init__(self):
            self.jobs = []

        def enqueue(self, job):
            self.jobs.append(job)

    provider = FakeProvider(responses=[])
    executor = Executor(provider)
    agent = GreeterAgent()
    run = Run(input="hello")
    queue = DeferredQueue()

    run_later(agent, run, executor, queue=queue)

    # provenance is set even though the job hasn't run yet
    assert run.agent_name == "GreeterAgent"
    assert queue.jobs  # sanity: the job really is still pending


class DeferredDurableQueue:
    """A DurableQueue whose `enqueue_run()` doesn't run the job immediately,
    unlike `FakeDurableQueue` above, so a test can inspect state between
    queuing and dispatch, the way a process crash would leave things.
    """

    def __init__(self) -> None:
        self.enqueued: list[str] = []
        self.jobs: dict[str, object] = {}
        self.forgotten: list[str] = []

    def enqueue(self, job):
        self.jobs["_"] = job

    def enqueue_run(self, run_id, job):
        self.enqueued.append(run_id)
        self.jobs[run_id] = job

    def pending(self) -> list[str]:
        return [rid for rid in self.enqueued if rid not in self.forgotten]

    def forget(self, run_id: str) -> None:
        self.forgotten.append(run_id)


def test_run_later_saves_to_the_default_run_store_before_a_durable_queue_dispatches(
    monkeypatch,
):
    store = InMemoryRunStore()
    monkeypatch.setattr(application.config, "run_store", store)
    provider = FakeProvider(responses=[])
    executor = Executor(provider)
    agent = GreeterAgent()
    run = Run(input="hello")
    queue = DeferredDurableQueue()

    run_later(agent, run, executor, queue=queue)

    # saved while still QUEUED: the job hasn't run yet
    saved = store.get(run.id)
    assert saved is not None
    assert saved.status == RunStatus.QUEUED
    assert saved.agent_name == "GreeterAgent"


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


def test_recover_pending_works_without_a_conversation_store_when_no_conversation():
    run_store = InMemoryRunStore()
    orphaned = _queued_run(agent_name="GreeterAgent")
    assert orphaned.conversation_id is None
    run_store.save(orphaned)
    queue = FakeDurableQueue(pending_ids=[orphaned.id])
    provider = FakeProvider(responses=[Message(role=Role.ASSISTANT, content="hi")])
    executor = Executor(provider)

    # no conversation_store given at all: fine, since this Run doesn't need one
    recovered = recover_pending(queue, run_store, executor, agents=[GreeterAgent])

    assert recovered == [orphaned]
    assert orphaned.status == RunStatus.COMPLETED


def _queued_run_with_conversation(
    *, agent_name: str, conversation_id: str, input: str = "hello"
) -> Run:
    run = Run(input=input, agent_name=agent_name, conversation_id=conversation_id)
    run.queue()
    return run


def test_recover_pending_resolves_the_conversation_through_the_given_store():
    conversation = Conversation()
    conversation.messages = [
        Message(role=Role.USER, content="earlier question"),
        Message(role=Role.ASSISTANT, content="earlier answer"),
    ]
    conversation_store = InMemoryConversationStore()
    conversation_store.save(conversation)

    run_store = InMemoryRunStore()
    orphaned = _queued_run_with_conversation(
        agent_name="GreeterAgent",
        conversation_id=conversation.id,
        input="new question",
    )
    run_store.save(orphaned)
    queue = FakeDurableQueue(pending_ids=[orphaned.id])
    provider = FakeProvider(
        responses=[Message(role=Role.ASSISTANT, content="new answer")]
    )
    executor = Executor(provider)

    recovered = recover_pending(
        queue,
        run_store,
        executor,
        agents=[GreeterAgent],
        conversation_store=conversation_store,
    )

    assert recovered == [orphaned]
    assert orphaned.status == RunStatus.COMPLETED
    # the resolved Conversation's history reached the model, alongside this
    # Run's own system prompt and turn: model context is a projection, not
    # a stored copy (GreeterAgent's instructions lead, per seed_run/model_context)
    contents = [m.content for m in provider.calls[0]["messages"]]
    assert contents == [
        "Say hello.",
        "earlier question",
        "earlier answer",
        "new question",
    ]
    # and this Run's own turn was folded back into the Conversation
    assert conversation.messages[-1].content == "new answer"


def test_recover_pending_fails_a_run_explicitly_when_no_conversation_store_is_given():
    run_store = InMemoryRunStore()
    orphaned = _queued_run_with_conversation(
        agent_name="GreeterAgent", conversation_id="conv-missing"
    )
    run_store.save(orphaned)
    queue = FakeDurableQueue(pending_ids=[orphaned.id])
    executor = Executor(FakeProvider(responses=[]))

    # conversation_store not given at all, but this Run needs one
    recovered = recover_pending(queue, run_store, executor, agents=[GreeterAgent])

    assert recovered == [orphaned]
    assert orphaned.status == RunStatus.FAILED
    assert "conv-missing" in orphaned.error
    assert queue.enqueued == []  # never handed to the queue for execution
    # persisted, not just mutated in memory
    assert run_store.get(orphaned.id).status == RunStatus.FAILED


def test_recover_pending_fails_a_run_explicitly_when_the_conversation_is_missing():
    run_store = InMemoryRunStore()
    orphaned = _queued_run_with_conversation(
        agent_name="GreeterAgent", conversation_id="conv-missing"
    )
    run_store.save(orphaned)
    queue = FakeDurableQueue(pending_ids=[orphaned.id])
    executor = Executor(FakeProvider(responses=[]))
    conversation_store = InMemoryConversationStore()  # empty: never saved conv-missing

    recovered = recover_pending(
        queue,
        run_store,
        executor,
        agents=[GreeterAgent],
        conversation_store=conversation_store,
    )

    assert recovered == [orphaned]
    assert orphaned.status == RunStatus.FAILED
    assert "conv-missing" in orphaned.error
    assert queue.enqueued == []


def test_recover_pending_does_not_repeatedly_recover_a_run_that_failed_to_resolve():
    run_store = InMemoryRunStore()
    orphaned = _queued_run_with_conversation(
        agent_name="GreeterAgent", conversation_id="conv-missing"
    )
    run_store.save(orphaned)
    queue = FakeDurableQueue(pending_ids=[orphaned.id])
    executor = Executor(FakeProvider(responses=[]))

    first = recover_pending(queue, run_store, executor, agents=[GreeterAgent])
    assert first == [orphaned]
    assert orphaned.status == RunStatus.FAILED

    # the journal no longer reports this run id as pending...
    assert queue.pending() == []

    # ...so a second recovery attempt (e.g. the next process restart) does
    # not rediscover it, and does not try (and fail) to fail it again
    second = recover_pending(queue, run_store, executor, agents=[GreeterAgent])
    assert second == []
    assert orphaned.status == RunStatus.FAILED  # unchanged, not re-processed
