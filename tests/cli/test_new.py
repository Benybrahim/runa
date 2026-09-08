"""Tests for `runa.cli.new`: `scaffold_project`."""

from pathlib import Path

import pytest

from runa.cli.new import ProjectAlreadyExists, scaffold_project


def test_scaffold_project_creates_the_conventional_app_layout(tmp_path: Path) -> None:
    """`scaffold_project` creates every `app/` subdir plus the project's own top-level files."""
    project_dir = scaffold_project("demo", root=tmp_path)

    assert project_dir == tmp_path / "demo"
    for subdir in ("agents", "tools", "resources", "evaluations", "tests"):
        assert (project_dir / "app" / subdir / "__init__.py").is_file()
    for name in ("pyproject.toml", "README.md", "main.py", ".gitignore", ".env"):
        assert (project_dir / name).is_file()


def test_scaffold_project_raises_if_the_directory_already_exists(tmp_path: Path) -> None:
    """`scaffold_project` refuses to overwrite an existing directory."""
    (tmp_path / "demo").mkdir()

    with pytest.raises(ProjectAlreadyExists):
        scaffold_project("demo", root=tmp_path)


def test_main_py_only_loads_dotenv_with_no_configure_step(tmp_path: Path) -> None:
    """The generated `main.py` has no `configure()`/provider wiring left over from the old CLI."""
    project_dir = scaffold_project("demo", root=tmp_path)

    main_py = (project_dir / "main.py").read_text()

    assert "load_dotenv()" in main_py
    assert "configure(" not in main_py
