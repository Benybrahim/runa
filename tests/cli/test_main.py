import pytest

from runa.cli.main import main
from runa.core import Run
from runa.persistence import SQLiteRunStore


def test_new_scaffolds_a_project(tmp_path, capsys):
    exit_code = main(["new", "acme"], cwd=tmp_path)

    assert exit_code == 0
    assert (tmp_path / "acme" / "app" / "agents" / "__init__.py").is_file()
    assert "created" in capsys.readouterr().out


def test_generate_agent_writes_into_the_project(tmp_path, capsys):
    main(["new", "acme"], cwd=tmp_path)
    project_dir = tmp_path / "acme"

    exit_code = main(["generate", "agent", "Support"], cwd=project_dir)

    assert exit_code == 0
    assert (project_dir / "app" / "agents" / "support_agent.py").is_file()
    assert "created" in capsys.readouterr().out


def test_missing_command_exits_nonzero():
    with pytest.raises(SystemExit):
        main([])


def test_generate_requires_a_kind():
    with pytest.raises(SystemExit):
        main(["generate"])


def test_eval_reports_pass_fail_and_exit_code(tmp_path, capsys):
    project_dir = tmp_path / "acme"
    main(["new", "acme"], cwd=tmp_path)
    (project_dir / "main.py").write_text(
        "from runa import configure\n"
        "from tests.fakes import FakeProvider\n"
        "from runa.core import Message, Role\n\n"
        "configure(provider=FakeProvider(responses=["
        'Message(role=Role.ASSISTANT, content="hi")]))\n'
    )
    (project_dir / "app" / "evaluations" / "echo_eval.py").write_text(
        "from runa import Agent, EvalCase, expect\n\n\n"
        "class EchoAgent(Agent):\n"
        '    instructions = "Echo."\n\n\n'
        "agent = EchoAgent()\n"
        "cases = [EvalCase(name='says hi', input='hi', "
        "check=lambda run: expect(run).to_contain('hi'))]\n"
    )

    exit_code = main(["eval"], cwd=project_dir)

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "says hi: PASS" in output
    assert "1/1 passed" in output


def test_runs_show_renders_a_saved_runs_timeline(tmp_path, capsys):
    project_dir = tmp_path / "acme"
    main(["new", "acme"], cwd=tmp_path)
    db_path = str(tmp_path / "runs.db")
    (project_dir / "main.py").write_text(
        "from runa import configure\n"
        "from runa.persistence import SQLiteRunStore\n"
        "from tests.fakes import FakeProvider\n\n"
        "configure(provider=FakeProvider(responses=[]), "
        f"run_store=SQLiteRunStore({db_path!r}))\n"
    )
    store = SQLiteRunStore(db_path)
    run = Run(input="hello")
    run.start()
    run.complete(result="hi")
    store.save(run)
    store.close()

    exit_code = main(["runs", "show", run.id], cwd=project_dir)

    output = capsys.readouterr().out
    assert exit_code == 0
    assert run.id in output
    assert "run completed" in output


def test_runs_requires_an_action():
    with pytest.raises(SystemExit):
        main(["runs"])
