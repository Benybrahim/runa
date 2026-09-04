import threading

from runa.agent import Agent
from runa.background import SQLiteQueue, recover_pending, run_later
from runa.core import Message, Role, Run, RunStatus
from runa.persistence import SQLiteRunStore
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


def test_concurrent_enqueue_run_from_multiple_threads_does_not_corrupt_the_journal(
    tmp_path,
):
    # check_same_thread=False only lifts sqlite3's same-thread check; the
    # shared Connection still isn't safe under real overlap between caller
    # threads calling enqueue_run() and worker threads clearing rows in
    # wrapped()'s finally block, without external locking.
    queue = SQLiteQueue(str(tmp_path / "queue.db"), max_workers=8)
    errors: list[Exception] = []
    barrier = threading.Barrier(8)

    def submit(worker_id: int) -> None:
        barrier.wait()
        for i in range(25):
            run_id = f"run-{worker_id}-{i}"
            try:
                queue.enqueue_run(run_id, lambda: None)
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

    threads = [threading.Thread(target=submit, args=(i,)) for i in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    queue.close(wait=True)

    assert errors == []


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


def test_run_later_saves_the_terminal_status_once_a_durable_job_completes(
    tmp_path, monkeypatch
):
    # Before this, run_later() only saved the Run once, as QUEUED, before
    # dispatch — nothing wrote the COMPLETED status back, so the store (and
    # `runa runs show <id>`) would show the Run as forever QUEUED even
    # though it finished successfully.
    run_store = SQLiteRunStore(str(tmp_path / "runs.db"))
    monkeypatch.setattr("runa.config._default_run_store", run_store)
    queue = SQLiteQueue(str(tmp_path / "queue.db"), max_workers=1)
    provider = FakeProvider(responses=[Message(role=Role.ASSISTANT, content="hi")])
    executor = Executor(provider)
    agent = GreeterAgent()
    run = Run(input="hello")

    run_later(agent, run, executor, queue=queue)
    queue.close(wait=True)

    saved = run_store.get(run.id)
    assert saved.status == RunStatus.COMPLETED
    assert saved.result == "hi"


def test_run_later_saves_a_failed_status_once_a_durable_job_fails(
    tmp_path, monkeypatch
):
    # Same gap as above, but for failure: a background Run that errors out
    # must not leave the store silently claiming it's still QUEUED — that
    # would hide the failure from anyone inspecting the store.
    run_store = SQLiteRunStore(str(tmp_path / "runs.db"))
    monkeypatch.setattr("runa.config._default_run_store", run_store)
    queue = SQLiteQueue(str(tmp_path / "queue.db"), max_workers=1)
    provider = FakeProvider(responses=[])  # raises on the first call
    executor = Executor(provider)
    agent = GreeterAgent()
    run = Run(input="hello")

    run_later(agent, run, executor, queue=queue)
    queue.close(wait=True)

    saved = run_store.get(run.id)
    assert saved.status == RunStatus.FAILED
    assert saved.error


def test_recover_pending_resumes_a_run_orphaned_by_a_crashed_process(tmp_path):
    queue_path = str(tmp_path / "queue.db")
    run_store_path = str(tmp_path / "runs.db")

    # Simulate the previous process: journal a run and persist it as QUEUED,
    # then crash before the job could clear the pending_jobs row (same setup
    # as test_pending_survives_reopening_the_same_database above).
    run = Run(input="hello", agent_name="GreeterAgent")
    run.queue()
    crashed_store = SQLiteRunStore(run_store_path)
    crashed_store.save(run)
    crashed_queue = SQLiteQueue(queue_path)
    crashed_queue._connection.execute(
        "INSERT INTO pending_jobs (run_id) VALUES (?)", (run.id,)
    )
    crashed_queue._connection.commit()
    crashed_queue.close(wait=False)
    crashed_store.close()

    # A new process reopens both and recovers.
    run_store = SQLiteRunStore(run_store_path)
    queue = SQLiteQueue(queue_path, max_workers=1)
    provider = FakeProvider(responses=[Message(role=Role.ASSISTANT, content="hi")])
    executor = Executor(provider)

    recovered = recover_pending(queue, run_store, executor, agents=[GreeterAgent])
    # enqueue_run() dispatches to the thread pool and returns immediately —
    # wait for it to drain before checking pending(), without closing the
    # connection pending() itself needs.
    queue._executor.shutdown(wait=True)

    assert [r.id for r in recovered] == [run.id]
    assert queue.pending() == []
    queue.close(wait=False)
    reloaded = run_store.get(run.id)
    assert reloaded.status == RunStatus.COMPLETED
    assert reloaded.result == "hi"
