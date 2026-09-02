from runa.agent import Agent
from runa.background import InlineQueue, run_later
from runa.core import Message, Role, Run, RunStatus
from runa.runtime import Executor
from tests.fakes import FakeProvider


class GreeterAgent(Agent):
    instructions = "Say hello."


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
