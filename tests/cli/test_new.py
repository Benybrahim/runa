import pytest

from runa.cli.new import ProjectAlreadyExists, scaffold_project


def test_scaffold_project_creates_the_conventional_layout(tmp_path):
    project_dir = scaffold_project("acme", root=tmp_path)

    assert project_dir == tmp_path / "acme"
    for subdir in ("agents", "tools", "resources", "evaluations"):
        package_dir = project_dir / "app" / subdir
        assert package_dir.is_dir()
        assert (package_dir / "__init__.py").is_file()

    assert (project_dir / "app" / "__init__.py").is_file()
    assert (project_dir / "pyproject.toml").is_file()
    assert (project_dir / "README.md").is_file()


def test_scaffold_project_writes_the_project_name_into_generated_files(tmp_path):
    project_dir = scaffold_project("acme", root=tmp_path)

    pyproject = (project_dir / "pyproject.toml").read_text()
    readme = (project_dir / "README.md").read_text()

    assert 'name = "acme"' in pyproject
    assert "# acme" in readme


def test_scaffold_project_raises_if_the_directory_already_exists(tmp_path):
    scaffold_project("acme", root=tmp_path)

    with pytest.raises(ProjectAlreadyExists):
        scaffold_project("acme", root=tmp_path)
