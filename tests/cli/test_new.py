import pytest

from runa.cli.new import ProjectAlreadyExists, scaffold_project


def test_scaffold_project_creates_the_conventional_layout(tmp_path):
    project_dir = scaffold_project("acme", root=tmp_path)

    assert project_dir == tmp_path / "acme"
    for subdir in ("agents", "tools", "resources", "evaluations", "tests"):
        package_dir = project_dir / "app" / subdir
        assert package_dir.is_dir()
        assert (package_dir / "__init__.py").is_file()

    assert (project_dir / "app" / "__init__.py").is_file()
    assert (project_dir / "pyproject.toml").is_file()
    assert (project_dir / "README.md").is_file()
    assert (project_dir / "main.py").is_file()


def test_scaffold_project_writes_a_main_py_that_calls_configure(tmp_path):
    project_dir = scaffold_project("acme", root=tmp_path)

    main_py = (project_dir / "main.py").read_text()

    assert "configure(provider=" in main_py


def test_scaffold_project_wires_up_a_durable_run_store(tmp_path):
    """`runa runs show`/`list` must work on a fresh project with no extra
    configuration: the library's own `configure()` default RunStore is
    in-memory, so the generated main.py has to opt into SQLiteRunStore
    itself, and the db file it writes belongs in .gitignore, not a commit."""
    project_dir = scaffold_project("acme", root=tmp_path)

    main_py = (project_dir / "main.py").read_text()
    assert "SQLiteRunStore(" in main_py
    assert "run_store=" in main_py

    gitignore = (project_dir / ".gitignore").read_text()
    assert "runa.db" in gitignore


def test_scaffold_project_writes_a_gitignored_env_file(tmp_path):
    """A fresh project should never require `export OPENAI_API_KEY=...`
    in the shell: `.env` ships with the key main.py expects, and main.py
    loads it via `load_dotenv()`, so filling in `.env` is the only step."""
    project_dir = scaffold_project("acme", root=tmp_path)

    env_file = (project_dir / ".env").read_text()
    assert "OPENAI_API_KEY=" in env_file

    main_py = (project_dir / "main.py").read_text()
    assert "load_dotenv()" in main_py

    pyproject = (project_dir / "pyproject.toml").read_text()
    assert "python-dotenv" in pyproject

    gitignore = (project_dir / ".gitignore").read_text()
    assert ".env" in gitignore.splitlines()


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
