import threading

from runa.agent import Agent
from runa.background import SQLiteQueue, run_later
from runa.core import Message, Role, Run, RunStatus
from runa.runtime import Executor
from tests.fakes import FakeProvider


class GreeterAgent(Agent):
    instructions = "Say hello."


def test_jobs_run_and_complete_on_a_background_thread(tmp_path):
    queue = SQLiteQueue(str(tmp_path / "queue.db"), max_workers=2)
    seen_thread = []

    def job() -> None:
        seen_thread.append(threading.current_thread())

    queue.enqueue(job)
    queue.close(wait=True)

    assert len(seen_thread) == 1
    assert seen_thread[0] is not threading.main_thread()


def test_run_later_journals_and_clears_the_run_id(tmp_path):
    release = threading.Event()
    started = threading.Event()
    queue = SQLiteQueue(str(tmp_path / "queue.db"), max_workers=1)

    provider = FakeProvider(responses=[Message(role=Role.ASSISTANT, content="hi")])
    executor = Executor(provider)
    agent = GreeterAgent()
    run = Run(input="hello")

    original_run = executor.run

    def blocking_run(agent, run):
        started.set()
        release.wait(timeout=5)
        return original_run(agent, run)

    executor.run = blocking_run

    run_later(agent, run, executor, queue=queue)
    assert started.wait(timeout=5)
    assert queue.pending() == [run.id]

    release.set()
    queue._executor.shutdown(wait=True)

    assert queue.pending() == []
    assert run.status == RunStatus.COMPLETED


def test_pending_survives_reopening_the_same_database(tmp_path):
    path = str(tmp_path / "queue.db")
    queue = SQLiteQueue(path)
    # Simulate a previous process that journaled a run and crashed before
    # its job could clear the row — write the row directly rather than
    # going through enqueue_run(), which would race its own worker thread
    # against the close() below.
    queue._connection.execute(
        "INSERT INTO pending_jobs (run_id) VALUES (?)", ("orphaned-run",)
    )
    queue._connection.commit()
    queue.close(wait=False)

    reopened = SQLiteQueue(path)
    assert reopened.pending() == ["orphaned-run"]


def test_run_later_with_sqlite_queue_completes_once_the_queue_drains(tmp_path):
    provider = FakeProvider(responses=[Message(role=Role.ASSISTANT, content="hi")])
    executor = Executor(provider)
    agent = GreeterAgent()
    run = Run(input="hello")
    queue = SQLiteQueue(str(tmp_path / "queue.db"), max_workers=1)

    result = run_later(agent, run, executor, queue=queue)
    queue.close(wait=True)

    assert result is run
    assert result.status == RunStatus.COMPLETED
    assert result.result == "hi"
