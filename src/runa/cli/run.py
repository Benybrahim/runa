"""cli/run.py: `runa run`, invoke an Agent from argv.

The CLI never contains logic of its own (see cli.md): this is a thin
wrapper over the same `Agent.run()` a developer would call from `main.py`.
The Run is saved to the app's configured RunStore afterward
(`application.run_store.save(run)`), the same explicit step
docs/guides.md's "Inspecting Runs" asks a developer to take, so `runa runs
show <id>` can find it right after `runa run` prints it, without requiring
a durable Queue or any other background-execution machinery.
"""

import importlib
import inspect
from pathlib import Path

from runa.agent import Agent
from runa.application import application
from runa.cli._project import loaded_app
from runa.cli.generate import NotARunaProject


class AgentNotFound(Exception):
    """Raised when no Agent under `app/agents/` matches the given name."""


def _require_agents_dir(root: Path) -> Path:
    agents_dir = root / "app" / "agents"
    if not agents_dir.is_dir():
        raise NotARunaProject(
            f"{agents_dir} does not exist, run this from inside a Runa "
            "project created with `runa new`"
        )
    return agents_dir


def _iter_agent_classes(agents_dir: Path):
    for agent_file in sorted(agents_dir.glob("*.py")):
        if agent_file.stem == "__init__":
            continue
        module = importlib.import_module(f"app.agents.{agent_file.stem}")
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if (
                issubclass(obj, Agent)
                and obj is not Agent
                and obj.__module__ == module.__name__
            ):
                yield obj


def find_agent_class(name: str, *, agents_dir: Path) -> type[Agent]:
    """Find the Agent subclass named `name` under `agents_dir`.

    Matches either the exact class name or, following `runa generate
    agent`'s own convention, `name` with an `Agent` suffix appended, so
    `runa run Support ...` finds `SupportAgent` without spelling out the
    suffix.
    """
    candidates = {name, name if name.endswith("Agent") else f"{name}Agent"}
    for agent_cls in _iter_agent_classes(agents_dir):
        if agent_cls.__name__ in candidates or agent_cls.agent_name() in candidates:
            return agent_cls
    raise AgentNotFound(f"no Agent named {name!r} found under {agents_dir}")


def run_agent(name: str, input: str, *, root: Path) -> str:
    """Run the named Agent against `input`, save the Run, and format it."""
    agents_dir = _require_agents_dir(root)

    with loaded_app(root):
        agent_cls = find_agent_class(name, agents_dir=agents_dir)
        run = agent_cls.run(input)
        application.run_store.save(run)

    header = f"Run {run.id} ({run.status.value})"
    if run.result is None:
        return header
    return f"{header}\n{run.result}"
