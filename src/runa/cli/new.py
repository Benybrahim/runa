"""cli/new.py: scaffold a new Runa application.

Establishes the conventional `app/` layout (manifesto §2) so a fresh
project has somewhere obvious to put agents, tools, resources, and eval
cases without any configuration.
"""

from pathlib import Path

_SUBDIRS = ("agents", "tools", "resources", "evaluations")

_PYPROJECT_TEMPLATE = """[project]
name = "{name}"
version = "0.1.0"
requires-python = ">=3.14"
dependencies = ["runa"]
"""

_README_TEMPLATE = """# {name}

A Runa application.

## Layout

- `app/agents/` — Agent subclasses
- `app/tools/` — Tool subclasses
- `app/resources/` — shared resources (clients, config)
- `app/evaluations/` — eval cases

Generate a new agent with:

    runa generate agent MyAgent
"""


class ProjectAlreadyExists(Exception):
    """Raised when `runa new` targets a directory that already exists."""


def scaffold_project(name: str, *, root: Path) -> Path:
    """Create `root/name` with the conventional Runa `app/` layout."""
    project_dir = root / name
    if project_dir.exists():
        raise ProjectAlreadyExists(f"{project_dir} already exists")

    app_dir = project_dir / "app"
    for subdir in _SUBDIRS:
        package_dir = app_dir / subdir
        package_dir.mkdir(parents=True)
        (package_dir / "__init__.py").write_text("")
    (app_dir / "__init__.py").write_text("")

    (project_dir / "pyproject.toml").write_text(_PYPROJECT_TEMPLATE.format(name=name))
    (project_dir / "README.md").write_text(_README_TEMPLATE.format(name=name))

    return project_dir
