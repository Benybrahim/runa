"""Tests for `runa.cli.main`: argv parsing, dispatch, and clean error reporting."""

from pathlib import Path

import pytest

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


def test_chat_reports_agent_not_found_as_a_clean_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`runa chat` on an unknown Agent name prints one clean line and exits 1, not a traceback."""
    project_dir = scaffold_project("demo", root=tmp_path)

    exit_code = main(["chat", "Nope"], cwd=project_dir)

    assert exit_code == 1
    assert "no Agent named 'Nope'" in capsys.readouterr().err


def test_chat_dispatches_to_run_agent_repl(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`runa chat Support` calls `run_agent_repl`, asking for a fresh session by default."""
    project_dir = scaffold_project("demo", root=tmp_path)
    calls: list[tuple[str, Path, str | None, bool, str | None]] = []

    def fake_repl(
        name: str,
        *,
        root: Path,
        session_id: str | None = None,
        continue_last: bool = False,
        resume: str | None = None,
    ) -> None:
        calls.append((name, root, session_id, continue_last, resume))

    monkeypatch.setattr("runa.cli.main.run_agent_repl", fake_repl)

    exit_code = main(["chat", "Support"], cwd=project_dir)

    assert exit_code == 0
    assert calls == [("Support", project_dir, None, False, None)]


def test_chat_continue_flag_dispatches_continue_last(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`runa chat Support --continue` (and its `-c` alias) asks to resume the last session."""
    project_dir = scaffold_project("demo", root=tmp_path)
    calls: list[bool] = []

    def fake_repl(
        name: str,
        *,
        root: Path,
        session_id: str | None = None,
        continue_last: bool = False,
        resume: str | None = None,
    ) -> None:
        calls.append(continue_last)

    monkeypatch.setattr("runa.cli.main.run_agent_repl", fake_repl)

    assert main(["chat", "Support", "--continue"], cwd=project_dir) == 0
    assert main(["chat", "Support", "-c"], cwd=project_dir) == 0
    assert calls == [True, True]


def test_chat_resume_flag_dispatches_the_given_or_empty_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--resume ID` passes the id through; bare `--resume` passes `""` to trigger a picker."""
    project_dir = scaffold_project("demo", root=tmp_path)
    calls: list[str | None] = []

    def fake_repl(
        name: str,
        *,
        root: Path,
        session_id: str | None = None,
        continue_last: bool = False,
        resume: str | None = None,
    ) -> None:
        calls.append(resume)

    monkeypatch.setattr("runa.cli.main.run_agent_repl", fake_repl)

    assert main(["chat", "Support", "--resume", "Support-old"], cwd=project_dir) == 0
    assert main(["chat", "Support", "--resume"], cwd=project_dir) == 0
    assert calls == ["Support-old", ""]


def test_chat_with_no_name_or_flags_reports_a_clean_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`runa chat` with no Agent name and no `--list`/`--show` prints a clean error."""
    project_dir = scaffold_project("demo", root=tmp_path)

    exit_code = main(["chat"], cwd=project_dir)

    assert exit_code == 1
    assert "needs an Agent name" in capsys.readouterr().err


def test_missing_main_py_reports_a_clean_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Running a command against a directory with no `main.py` prints one clean line."""
    (tmp_path / "tests").mkdir(parents=True)

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
    (project_dir / "tests" / "test_smoke.py").write_text(
        "def test_bad():\n    assert False, 'nope'\n"
    )

    exit_code = main(["test"], cwd=project_dir)

    out = capsys.readouterr().out
    assert exit_code == 1
    assert "FAIL: nope" in out
    assert "0/1 passed" in out


def test_chat_list_reports_no_sessions(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """`runa chat --list` against a fresh project reports no sessions."""
    project_dir = scaffold_project("demo", root=tmp_path)

    exit_code = main(["chat", "--list"], cwd=project_dir)

    assert exit_code == 0
    assert "no sessions found" in capsys.readouterr().out


def test_chat_show_reports_unknown_session_as_a_clean_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`runa chat --show` on an unknown session id prints a clean error."""
    project_dir = scaffold_project("demo", root=tmp_path)

    exit_code = main(["chat", "--show", "nope"], cwd=project_dir)

    assert exit_code == 1
    assert "no session found" in capsys.readouterr().err
