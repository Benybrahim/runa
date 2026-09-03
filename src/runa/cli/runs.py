"""cli/runs.py: `runa runs show <id>` — render a Run's timeline.

Manifesto §11 asks that "what happened?" have an answer without adding
tracing code to every agent. This is a thin read over `default_run_store()`
and `timeline()` — both already exist; this only wires them to argv. Only
useful once an app configures a durable `RunStore` (see `config.py`), since
the default is in-memory and won't outlive the process that created the run.
"""

from pathlib import Path

from runa.cli._project import loaded_app
from runa.config import default_run_store
from runa.core import Run
from runa.observability import timeline


class RunNotFound(Exception):
    """Raised when `runa runs show` is given an id not in the RunStore."""


def format_run_timeline(run: Run) -> str:
    lines = [f"Run {run.id} ({run.status.value})", ""]
    for entry in timeline(run):
        lines.append(f"{entry.timestamp.isoformat()}  {entry.summary}")
    return "\n".join(lines)


def show_run(run_id: str, *, root: Path) -> str:
    """Look up `run_id` in the app's configured RunStore and render its timeline."""
    with loaded_app(root):
        run = default_run_store().get(run_id)

    if run is None:
        raise RunNotFound(f"no run found with id {run_id!r}")
    return format_run_timeline(run)
