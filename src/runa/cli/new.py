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
dependencies = ["runa", "python-dotenv"]
"""

_MAIN_TEMPLATE = '''"""main.py: the application entry point.

The one place to call `configure()`. A model Provider is an app-wide
dependency (manifesto §2), not a per-agent one, so it's set once here
rather than at each call site: swap OpenAIProvider/AsyncOpenAIProvider for
AnthropicProvider/AsyncAnthropicProvider (or any other Provider) as this
app's needs change. `async_provider` is what `Agent.run()`/`.run_sync()`/
`.run_stream()`/`.run_later()` actually drive: Runa's canonical execution
model is async (see docs/concepts.md). `load_dotenv()` reads the key(s) out
of `.env` (see that file) so every `runa` command picks them up without
exporting anything into the shell.

`run_store=SQLiteRunStore("runa.db")` makes `runa runs show`/`list` work
right away: `runa.configure()`'s own default RunStore is in-memory and
would silently lose every Run the moment this process exits, which the
generated project shouldn't ask a new developer to discover on their own.
Swap it for another RunStore, or drop it back
to the library default, as this app's needs change.
"""

from dotenv import load_dotenv

from runa import configure
from runa.persistence import SQLiteRunStore
from runa.providers import AsyncOpenAIProvider, OpenAIProvider

load_dotenv()
configure(
    provider=OpenAIProvider(),
    async_provider=AsyncOpenAIProvider(),
    run_store=SQLiteRunStore("runa.db"),
)


if __name__ == "__main__":
    # from app.agents.example_agent import ExampleAgent
    #
    # run = ExampleAgent.run_sync("...")
    # print(run.result)
    pass
'''

_ENV_TEMPLATE = """# Loaded by main.py via load_dotenv(). Fill in the API key for
# whichever Provider main.py configures, then never commit this file.
OPENAI_API_KEY=
"""

_GITIGNORE_TEMPLATE = """__pycache__/
*.pyc
runa.db
.env
"""

_README_TEMPLATE = """# {name}

A Runa application.

## Layout

- `main.py`: application entry point, calls `configure()`
- `.env`: your provider's API key, gitignored; fill it in before running
- `app/agents/`: Agent subclasses
- `app/tools/`: Tool subclasses
- `app/resources/`: shared resources (clients, config)
- `app/evaluations/`: eval cases, run with `runa eval`
- `app/tests/`: deterministic tests, run with `runa test`
- `runa.db`: this app's Run history (see `main.py`); inspect it with
  `runa runs show`/`list`, don't commit it

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
    (project_dir / ".gitignore").write_text(_GITIGNORE_TEMPLATE)
    (project_dir / ".env").write_text(_ENV_TEMPLATE)

    return project_dir
