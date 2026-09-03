import pytest

from runa.cli.main import main
from runa.core import Message, Role, Run, RunStatus, ToolCall
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


def test_test_reports_pass_fail_and_exit_code(tmp_path, capsys):
    project_dir = tmp_path / "acme"
    main(["new", "acme"], cwd=tmp_path)
    (project_dir / "main.py").write_text(
        "from runa import configure\n"
        "from tests.fakes import FakeProvider\n"
        "from runa.core import Message, Role\n\n"
        "configure(provider=FakeProvider(responses=["
        'Message(role=Role.ASSISTANT, content="hi")]))\n'
    )
    (project_dir / "app" / "tests" / "echo_test.py").write_text(
        "from runa import Agent\n\n\n"
        "class EchoAgent(Agent):\n"
        '    instructions = "Echo."\n\n\n'
        "def test_says_hi():\n"
        '    run = EchoAgent.run("hi")\n'
        '    assert run.result == "hi"\n'
    )

    exit_code = main(["test"], cwd=project_dir)

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "echo_test.test_says_hi: PASS" in output
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


def test_runs_list_filters_by_status(tmp_path, capsys):
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
    completed = Run(input="hello")
    completed.start()
    completed.complete(result="hi")
    failed = Run(input="oops")
    failed.start()
    failed.fail("boom")
    store.save(completed)
    store.save(failed)
    store.close()

    exit_code = main(["runs", "list", "--status", "failed"], cwd=project_dir)

    output = capsys.readouterr().out
    assert exit_code == 0
    assert failed.id in output
    assert completed.id not in output


def test_runs_requires_an_action():
    with pytest.raises(SystemExit):
        main(["runs"])


def _new_project_with_store(tmp_path):
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
    return project_dir, db_path


def test_runs_pending_and_approve_resume_a_run(tmp_path, capsys):
    project_dir, db_path = _new_project_with_store(tmp_path)
    store = SQLiteRunStore(db_path)
    call = ToolCall(name="SendEmail", arguments={"to": "a@example.com"})
    run = Run(input="email someone")
    run.start()
    run.add_message(Message(role=Role.ASSISTANT, tool_calls=[call]))
    run.require_approval(call.id)
    store.save(run)
    store.close()

    pending_exit = main(["runs", "pending"], cwd=project_dir)
    pending_output = capsys.readouterr().out
    assert pending_exit == 0
    assert run.id in pending_output
    assert "SendEmail" in pending_output

    approve_exit = main(["runs", "approve", run.id, call.id], cwd=project_dir)
    approve_output = capsys.readouterr().out
    assert approve_exit == 0
    assert "approved" in approve_output

    store = SQLiteRunStore(db_path)
    saved = store.get(run.id)
    store.close()
    assert saved.status == RunStatus.RUNNING
    assert saved.tool_calls[0].approved is True


def test_runs_deny_fails_a_run(tmp_path, capsys):
    project_dir, db_path = _new_project_with_store(tmp_path)
    store = SQLiteRunStore(db_path)
    call = ToolCall(name="SendEmail", arguments={"to": "a@example.com"})
    run = Run(input="email someone")
    run.start()
    run.add_message(Message(role=Role.ASSISTANT, tool_calls=[call]))
    run.require_approval(call.id)
    store.save(run)
    store.close()

    exit_code = main(
        ["runs", "deny", run.id, call.id, "--reason", "not authorized"],
        cwd=project_dir,
    )
    output = capsys.readouterr().out
    assert exit_code == 0
    assert "denied" in output

    store = SQLiteRunStore(db_path)
    saved = store.get(run.id)
    store.close()
    assert saved.status == RunStatus.FAILED
