"""cli/new.py: scaffold a new Runa application.

Establishes the conventional `app/` layout (manifesto §2) so a fresh
project has somewhere obvious to put agents, tools, resources, eval cases,
and tests without any configuration.
"""

from pathlib import Path

_SUBDIRS = ("agents", "tools", "resources", "evaluations", "tests")

_PYPROJECT_TEMPLATE = """[project]
name = "{name}"
version = "0.1.0"
requires-python = ">=3.14"
dependencies = ["runa"]
"""

_MAIN_TEMPLATE = '''"""main.py: the application entry point.

The one place to call `configure()`. A model Provider is an app-wide
dependency (manifesto §2), not a per-agent one, so it's set once here
rather than at each call site — swap OpenAIProvider for AnthropicProvider
(or any other Provider) as this app's needs change. Requires an API key
in the environment for whichever provider you use.
"""

from runa import configure
from runa.providers import OpenAIProvider

configure(provider=OpenAIProvider())


if __name__ == "__main__":
    # from app.agents.example_agent import ExampleAgent
    #
    # run = ExampleAgent.run("...")
    # print(run.result)
    pass
'''

_README_TEMPLATE = """# {name}

A Runa application.

## Layout

- `main.py` — application entry point, calls `configure()`
- `app/agents/` — Agent subclasses
- `app/tools/` — Tool subclasses
- `app/resources/` — shared resources (clients, config)
- `app/evaluations/` — eval cases, run with `runa eval`
- `app/tests/` — deterministic tests, run with `runa test`

Generate scaffolding with:

    runa generate agent MyAgent
    runa generate tool MyTool
    runa generate evaluation MyAgent
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
    (project_dir / "main.py").write_text(_MAIN_TEMPLATE)

    return project_dir
