"""cli/eval.py: `runa eval`, run evals/ datasets.

A thin loop that imports each `evals/` module and hands what it declares to `agent.evaluate()`,
the same code path production evaluation runs through, not a parallel CLI-only harness.
"""

import asyncio
import importlib
from pathlib import Path

from runa.cli._project import NotARunaProject, loaded_app
from runa.eval import Report


class InvalidEvalModule(Exception):
    """Raised when an `evals/` module doesn't declare `agent` and `dataset`."""


def run_project_evals(root: Path) -> list[Report]:
    """Import every `evals/` module and evaluate its agent against its dataset."""
    evals_dir = root / "evals"
    if not evals_dir.is_dir():
        raise NotARunaProject(
            f"{evals_dir} does not exist, run this from inside a Runa "
            "project created with `runa new`"
        )

    with loaded_app(root):
        modules = []
        for eval_file in sorted(evals_dir.glob("*.py")):
            if eval_file.stem == "__init__":
                continue
            module = importlib.import_module(f"evals.{eval_file.stem}")
            agent = getattr(module, "agent", None)
            dataset = getattr(module, "dataset", None)
            if agent is None or dataset is None:
                raise InvalidEvalModule(
                    f"{eval_file} must define module-level `agent` and `dataset`"
                )
            modules.append((agent, dataset))

        async def _run_all() -> list[Report]:
            return [await agent.evaluate(dataset) for agent, dataset in modules]

        return asyncio.run(_run_all())
