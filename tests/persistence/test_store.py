from datetime import UTC, datetime, timedelta

from runa.core import Run, RunStatus
from runa.persistence import InMemoryRunStore, RunStore


def test_save_and_get_round_trips_a_run():
    store = InMemoryRunStore()
    run = Run(input="hi")

    store.save(run)

    assert store.get(run.id) is run


def test_get_missing_run_returns_none():
    store = InMemoryRunStore()

    assert store.get("does-not-exist") is None


def test_list_returns_all_saved_runs():
    store = InMemoryRunStore()
    first = Run(input="one")
    second = Run(input="two")

    store.save(first)
    store.save(second)

    assert {run.id for run in store.list()} == {first.id, second.id}


def test_save_again_overwrites_the_previous_version():
    store = InMemoryRunStore()
    run = Run(input="hi")
    store.save(run)

    run.start()
    run.complete(result="done")
    store.save(run)

    reloaded = store.get(run.id)
    assert reloaded is not None
    assert reloaded.result == "done"
    assert len(store.list()) == 1


def test_list_filters_by_status():
    store = InMemoryRunStore()
    completed = Run(input="one")
    completed.start()
    completed.complete(result="done")
    failed = Run(input="two")
    failed.start()
    failed.fail("boom")
    store.save(completed)
    store.save(failed)

    assert store.list(status=RunStatus.COMPLETED) == [completed]
    assert store.list(status=RunStatus.FAILED) == [failed]


def test_list_filters_by_since():
    store = InMemoryRunStore()
    old = Run(input="old", created_at=datetime.now(UTC) - timedelta(days=1))
    recent = Run(input="recent")
    store.save(old)
    store.save(recent)

    assert store.list(since=datetime.now(UTC) - timedelta(hours=1)) == [recent]


def test_list_filters_by_agent_name():
    store = InMemoryRunStore()
    research = Run(input="one", agent_name="ResearchAgent")
    support = Run(input="two", agent_name="SupportAgent")
    store.save(research)
    store.save(support)

    assert store.list(agent_name="ResearchAgent") == [research]


def test_list_filters_by_parent_run_id():
    store = InMemoryRunStore()
    parent = Run(input="parent")
    child = Run(input="child", parent_run_id=parent.id)
    other = Run(input="unrelated")
    store.save(parent)
    store.save(child)
    store.save(other)

    assert store.list(parent_run_id=parent.id) == [child]


def test_list_filters_by_conversation_id():
    store = InMemoryRunStore()
    first = Run(input="one", conversation_id="conv-1")
    second = Run(input="two", conversation_id="conv-2")
    store.save(first)
    store.save(second)

    assert store.list(conversation_id="conv-1") == [first]


def test_list_combines_status_and_since_filters():
    store = InMemoryRunStore()
    old_failed = Run(input="old", created_at=datetime.now(UTC) - timedelta(days=1))
    old_failed.start()
    old_failed.fail("boom")
    recent_failed = Run(input="recent")
    recent_failed.start()
    recent_failed.fail("boom")
    store.save(old_failed)
    store.save(recent_failed)

    matches = store.list(
        status=RunStatus.FAILED, since=datetime.now(UTC) - timedelta(hours=1)
    )

    assert matches == [recent_failed]


def test_run_store_protocol_is_satisfiable_without_inheritance():
    class DictBackedStore:
        def __init__(self):
            self._runs = {}

        def save(self, run):
            self._runs[run.id] = run

        def get(self, run_id):
            return self._runs.get(run_id)

        def list(self, *, status=None, since=None, agent_name=None, parent_run_id=None):
            return [
                run
                for run in self._runs.values()
                if (status is None or run.status == status)
                and (since is None or run.created_at >= since)
                and (agent_name is None or run.agent_name == agent_name)
                and (parent_run_id is None or run.parent_run_id == parent_run_id)
            ]

    store: RunStore = DictBackedStore()
    run = Run(input="hi")
    store.save(run)

    assert store.get(run.id) is run
    assert store.list() == [run]
