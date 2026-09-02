import pytest

from runa.cli.main import main


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
