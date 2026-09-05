import pytest

from runa.cli.generate import NotARunaProject
from runa.cli.new import scaffold_project
from runa.cli.run import AgentNotFound, run_agent
from runa.persistence import SQLiteRunStore

_AGENT_MODULE = """
from runa import Agent


class EchoAgent(Agent):
    instructions = "Echo pleasantly."
"""


def _main_py(db_path: str) -> str:
    return (
        "from runa import configure\n"
        "from tests.fakes import FakeProvider\n"
        "from runa.core import Message, Role\n"
        "from runa.persistence import SQLiteRunStore\n\n"
        "configure(\n"
        "    provider=FakeProvider(responses=["
        'Message(role=Role.ASSISTANT, content="hi there")]),\n'
        f"    run_store=SQLiteRunStore({db_path!r}),\n"
        ")\n"
    )


def _scaffold_with_agent(tmp_path):
    project_dir = scaffold_project("acme", root=tmp_path)
    db_path = str(tmp_path / "runa.db")
    (project_dir / "main.py").write_text(_main_py(db_path))
    (project_dir / "app" / "agents" / "echo_agent.py").write_text(_AGENT_MODULE)
    return project_dir, db_path


def test_run_agent_by_exact_class_name(tmp_path):
    project_dir, _ = _scaffold_with_agent(tmp_path)

    output = run_agent("EchoAgent", "hello", root=project_dir)

    assert "COMPLETED" in output.upper()
    assert "hi there" in output


def test_run_agent_resolves_bare_name_to_agent_suffix(tmp_path):
    project_dir, _ = _scaffold_with_agent(tmp_path)

    output = run_agent("Echo", "hello", root=project_dir)

    assert "hi there" in output


def test_run_agent_saves_the_run_to_the_run_store(tmp_path):
    project_dir, db_path = _scaffold_with_agent(tmp_path)

    output = run_agent("Echo", "hello", root=project_dir)
    run_id = output.splitlines()[0].split()[1]

    store = SQLiteRunStore(db_path)
    saved = store.get(run_id)
    assert saved is not None
    assert saved.agent_name == "EchoAgent"


def test_run_agent_raises_for_an_unknown_agent_name(tmp_path):
    project_dir, _ = _scaffold_with_agent(tmp_path)

    with pytest.raises(AgentNotFound):
        run_agent("DoesNotExist", "hello", root=project_dir)


def test_run_agent_raises_outside_a_runa_project(tmp_path):
    with pytest.raises(NotARunaProject):
        run_agent("Echo", "hello", root=tmp_path)
