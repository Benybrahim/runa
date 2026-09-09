"""cli/new.py: scaffold a new Runa application.

Establishes the conventional project layout so a fresh project has somewhere obvious to put
agents, tools, prompts, and eval cases (under `app/`), plus tests, shared config, the SQLite
database, and developer docs (at the project root) without any configuration.
"""

from pathlib import Path

_APP_SUBDIRS = ("agents", "tools", "knowledge", "prompts", "evaluations")
_ROOT_PACKAGE_SUBDIRS = ("tests", "config")
_ROOT_PLAIN_SUBDIRS = ("db", "docs")

_PYPROJECT_TEMPLATE = """[project]
name = "{name}"
version = "0.1.0"
requires-python = ">=3.14"
dependencies = ["runa", "python-dotenv"]
"""

_MAIN_TEMPLATE = '''"""main.py: the application entry point.

Loads `.env` so every `runa` command (and this file, run directly) picks up
whichever API key(s) the agents below need, without exporting anything into
the shell. There's no separate configuration step beyond that: a model is a
per-`Agent` class attribute (see `app/agents/`), and Runa resolves it to the
right provider (OpenAI, Anthropic, Google, Meta, DeepSeek, or Alibaba) from
its name, so nothing here wires up a model or provider globally.
"""

from dotenv import load_dotenv

load_dotenv()


if __name__ == "__main__":
    # from app.agents.example_agent import ExampleAgent
    #
    # print(ExampleAgent().run_sync("...").output)
    pass
'''

_ENV_TEMPLATE = """# Loaded by main.py via load_dotenv(). Fill in the API key for whichever
# model(s) your agents use (see app/agents/), then never commit this file.
# OPENAI_API_KEY (gpt-*) / ANTHROPIC_API_KEY (claude-*) / GEMINI_API_KEY (gemini-*)
# LLAMA_API_KEY (llama-*) / DEEPSEEK_API_KEY (deepseek-*) / DASHSCOPE_API_KEY (qwen-*)
OPENAI_API_KEY=
"""

_GITIGNORE_TEMPLATE = """__pycache__/
*.pyc
db/runa.db
.env
"""

_README_TEMPLATE = """# {name}

A Runa application.

## Layout

- `main.py`: application entry point, loads `.env`
- `.env`: your model's API key, gitignored; fill it in before running
- `app/agents/`: Agent subclasses
- `app/tools/`: `@tool`-decorated functions
- `app/knowledge/`: files (Markdown, PDF, text, CSV) a `Knowledge()` retrieves from automatically
- `app/prompts/`: prompt text, kept out of Python source
- `app/evaluations/`: eval cases, run with `runa eval`
- `tests/`: deterministic tests, run with `runa test`
- `config/`: shared config (clients, settings)
- `db/runa.db`: conversation history and traces, see `runa chat --list`/`--show`; don't commit it
- `docs/`: developer documentation -- for agent-retrievable knowledge, see `app/knowledge/` instead

Generate scaffolding with:

    runa generate agent MyAgent
    runa generate tool MyTool
    runa generate prompt MyAgent
    runa generate evaluation MyAgent
"""


class ProjectAlreadyExists(Exception):
    """Raised when `runa new` targets a directory that already exists."""


def scaffold_project(name: str, *, root: Path) -> Path:
    """Create `root/name` with the conventional Runa project layout."""
    project_dir = root / name
    if project_dir.exists():
        raise ProjectAlreadyExists(f"{project_dir} already exists")

    app_dir = project_dir / "app"
    for subdir in _APP_SUBDIRS:
        package_dir = app_dir / subdir
        package_dir.mkdir(parents=True)
        (package_dir / "__init__.py").write_text("")
    (app_dir / "__init__.py").write_text("")

    for subdir in _ROOT_PACKAGE_SUBDIRS:
        package_dir = project_dir / subdir
        package_dir.mkdir(parents=True)
        (package_dir / "__init__.py").write_text("")

    for subdir in _ROOT_PLAIN_SUBDIRS:
        (project_dir / subdir).mkdir()

    (project_dir / "pyproject.toml").write_text(_PYPROJECT_TEMPLATE.format(name=name))
    (project_dir / "README.md").write_text(_README_TEMPLATE.format(name=name))
    (project_dir / "main.py").write_text(_MAIN_TEMPLATE)
    (project_dir / ".gitignore").write_text(_GITIGNORE_TEMPLATE)
    (project_dir / ".env").write_text(_ENV_TEMPLATE)

    return project_dir
