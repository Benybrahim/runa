import threading

from runa.agent import Agent
from runa.background import ThreadQueue, run_later
from runa.core import Context, Message, Role, Run, RunStatus
from runa.runtime import Executor
from tests.fakes import FakeProvider


class GreeterAgent(Agent):
    instructions = "Say hello."


def test_enqueue_returns_before_a_blocked_job_finishes():
    release = threading.Event()
    started = threading.Event()
    finished = threading.Event()
    queue = ThreadQueue(max_workers=1)

    def job() -> None:
        started.set()
        release.wait(timeout=5)
        finished.set()

    queue.enqueue(job)
    assert started.wait(timeout=5)
    assert not finished.is_set()

    release.set()
    queue.close(wait=True)
    assert finished.is_set()


def test_jobs_run_and_complete_on_a_background_thread():
    queue = ThreadQueue(max_workers=2)
    seen_thread = []

    def job() -> None:
        seen_thread.append(threading.current_thread())

    queue.enqueue(job)
    queue.close(wait=True)

    assert len(seen_thread) == 1
    assert seen_thread[0] is not threading.main_thread()


def test_run_later_with_thread_queue_completes_once_the_queue_drains():
    provider = FakeProvider(responses=[Message(role=Role.ASSISTANT, content="hi")])
    executor = Executor(provider)
    agent = GreeterAgent()
    run = Run(input="hello")
    queue = ThreadQueue(max_workers=1)

    result = run_later(agent, run, executor, queue=queue)
    queue.close(wait=True)

    assert result is run
    assert result.status == RunStatus.COMPLETED
    assert result.result == "hi"


def test_a_bug_before_the_step_loop_fails_the_run_instead_of_vanishing_on_the_worker():
    # A ThreadPoolExecutor swallows any exception a submitted job raises
    # unless something calls future.result(); nobody does here, since
    # run_later() is fire-and-forget by design. So an exception that
    # Executor.run() doesn't already convert into run.fail() would
    # otherwise disappear completely: no Run failure, no raised exception,
    # no trace anywhere. This proves Executor's seeding fix closes that gap
    # for the background path specifically, not just the synchronous one.
    class Unstringable:
        def __str__(self):
            raise RuntimeError("bug while rendering context")

    provider = FakeProvider(responses=[])
    executor = Executor(provider)
    agent = GreeterAgent()
    run = Run(input="hello", context=Context(bad=Unstringable()))
    queue = ThreadQueue(max_workers=1)

    result = run_later(agent, run, executor, queue=queue)
    queue.close(wait=True)

    assert result is run
    assert result.status == RunStatus.FAILED
    assert "bug while rendering context" in result.error
