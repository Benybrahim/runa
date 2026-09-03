import pytest

from runa.cli.new import scaffold_project
from runa.cli.runs import RunNotFound, show_run
from runa.core import Run
from runa.persistence import SQLiteRunStore

_MAIN_PY_TEMPLATE = """
from runa import configure
from runa.persistence import SQLiteRunStore
from tests.fakes import FakeProvider

configure(
    provider=FakeProvider(responses=[]),
    run_store=SQLiteRunStore({db_path!r}),
)
"""


def _scaffold_with_store(tmp_path):
    project_dir = scaffold_project("acme", root=tmp_path)
    db_path = str(tmp_path / "runs.db")
    (project_dir / "main.py").write_text(_MAIN_PY_TEMPLATE.format(db_path=db_path))
    return project_dir, db_path


def test_show_run_renders_a_saved_runs_timeline(tmp_path):
    project_dir, db_path = _scaffold_with_store(tmp_path)
    store = SQLiteRunStore(db_path)
    run = Run(input="hello")
    run.start()
    run.complete(result="hi")
    store.save(run)
    store.close()

    output = show_run(run.id, root=project_dir)

    assert run.id in output
    assert "run started" in output
    assert "run completed" in output


def test_show_run_raises_for_an_unknown_id(tmp_path):
    project_dir, _ = _scaffold_with_store(tmp_path)

    with pytest.raises(RunNotFound):
        show_run("does-not-exist", root=project_dir)
