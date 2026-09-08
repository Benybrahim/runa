"""Tests for `runa.cli.main`: argv parsing, dispatch, and clean error reporting."""

from pathlib import Path

import pytest
from agents.items import ToolApprovalItem
from openai.types.responses import ResponseFunctionToolCall

from runa.agent import Agent
from runa.cli._approvals import save_pending
from runa.cli.main import main
from runa.cli.new import scaffold_project


def test_new_scaffolds_a_project_and_prints_next_steps(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`runa new demo` scaffolds the project and prints next-step guidance."""
    exit_code = main(["new", "demo"], cwd=tmp_path)

    assert exit_code == 0
    assert (tmp_path / "demo" / "main.py").is_file()
    assert "created" in capsys.readouterr().out


def test_new_reports_an_existing_directory_as_a_clean_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`runa new` on an existing directory prints one clean line and exits 1."""
    (tmp_path / "demo").mkdir()

    exit_code = main(["new", "demo"], cwd=tmp_path)

    assert exit_code == 1
    assert "already exists" in capsys.readouterr().err


def test_generate_agent_dispatches_to_generate_agent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`runa generate agent Support` writes the agent file under the given cwd."""
    project_dir = scaffold_project("demo", root=tmp_path)

    exit_code = main(["generate", "agent", "Support"], cwd=project_dir)

    assert exit_code == 0
    assert (project_dir / "app" / "agents" / "support_agent.py").is_file()


def test_run_reports_agent_not_found_as_a_clean_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`runa run` on an unknown Agent name prints one clean line and exits 1, not a traceback."""
    project_dir = scaffold_project("demo", root=tmp_path)

    exit_code = main(["run", "Nope", "hi"], cwd=project_dir)

    assert exit_code == 1
    assert "no Agent named 'Nope'" in capsys.readouterr().err


def test_missing_main_py_reports_a_clean_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Running a command against a directory with no `main.py` prints one clean line."""
    (tmp_path / "app" / "tests").mkdir(parents=True)

    exit_code = main(["test"], cwd=tmp_path)

    assert exit_code == 1
    assert "no main.py found" in capsys.readouterr().err


def test_eval_reports_pass_fail_counts_and_exit_code(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`runa eval` against an empty `app/evaluations/` reports 0/0 passed and exits 0."""
    project_dir = scaffold_project("demo", root=tmp_path)

    exit_code = main(["eval"], cwd=project_dir)

    assert exit_code == 0
    assert "0/0 passed" in capsys.readouterr().out


def test_test_reports_a_failing_test_with_exit_code_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`runa test` exits 1 and reports the failure when a `test_*` function fails."""
    project_dir = scaffold_project("demo", root=tmp_path)
    (project_dir / "app" / "tests" / "test_smoke.py").write_text(
        "def test_bad():\n    assert False, 'nope'\n"
    )

    exit_code = main(["test"], cwd=project_dir)

    out = capsys.readouterr().out
    assert exit_code == 1
    assert "FAIL: nope" in out
    assert "0/1 passed" in out


def test_runs_list_reports_no_sessions(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """`runa runs list` against a fresh project reports no sessions."""
    project_dir = scaffold_project("demo", root=tmp_path)

    exit_code = main(["runs", "list"], cwd=project_dir)

    assert exit_code == 0
    assert "no sessions found" in capsys.readouterr().out


def test_runs_pending_reports_a_saved_pending_approval(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`runa runs pending` surfaces a row saved directly through `cli/_approvals.py`."""
    project_dir = scaffold_project("demo", root=tmp_path)
    agent = Agent(name="SupportAgent")
    interruption = ToolApprovalItem(
        agent=agent,
        raw_item=ResponseFunctionToolCall(
            call_id="call_1", name="delete_file", arguments="{}", type="function_call"
        ),
    )
    save_pending(
        project_dir / "runa.db",
        session_id="SupportAgent",
        agent_class_name="SupportAgent",
        interruptions=[interruption],
        state_json="{}",
    )

    exit_code = main(["runs", "pending"], cwd=project_dir)

    assert exit_code == 0
    assert "delete_file" in capsys.readouterr().out


def test_runs_cancel_reports_no_pending_approval_as_a_clean_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`runa runs cancel` on a session with nothing pending prints a clean error."""
    project_dir = scaffold_project("demo", root=tmp_path)

    exit_code = main(["runs", "cancel", "SupportAgent"], cwd=project_dir)

    assert exit_code == 1
    assert "no pending approval" in capsys.readouterr().err
