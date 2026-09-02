from runa.core import Run
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

    assert store.get(run.id).result == "done"
    assert len(store.list()) == 1


def test_run_store_protocol_is_satisfiable_without_inheritance():
    class DictBackedStore:
        def __init__(self):
            self._runs = {}

        def save(self, run):
            self._runs[run.id] = run

        def get(self, run_id):
            return self._runs.get(run_id)

        def list(self):
            return list(self._runs.values())

    store: RunStore = DictBackedStore()
    run = Run(input="hi")
    store.save(run)

    assert store.get(run.id) is run
    assert store.list() == [run]
