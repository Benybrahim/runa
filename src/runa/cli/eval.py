"""cli/eval.py: `runa eval`, run app/evaluations/ cases.

Manifesto §12 asks for `agent eval` as a command; this is a thin loop that
imports each `app/evaluations/` module and hands what it declares to
`run_evals()`, the same code path production runs through, not a parallel
CLI-only harness.
"""

import asyncio
import importlib
from pathlib import Path

from runa.application import application
from runa.cli._project import loaded_app
from runa.eval import EvalResult, run_evals
from runa.runtime import Executor


class NotARunaProject(Exception):
    """Raised when `app/evaluations/` isn't present under `root`."""


class InvalidEvalModule(Exception):
    """Raised when an app/evaluations/ module doesn't declare agent + cases."""


def run_project_evals(root: Path) -> list[EvalResult]:
    """Import every `app/evaluations/` module and run its eval cases."""
    evaluations_dir = root / "app" / "evaluations"
    if not evaluations_dir.is_dir():
        raise NotARunaProject(
            f"{evaluations_dir} does not exist, run this from inside a Runa "
            "project created with `runa new`"
        )

    with loaded_app(root):
        executor = Executor(provider=application.async_provider)

        modules = []
        for eval_file in sorted(evaluations_dir.glob("*.py")):
            if eval_file.stem == "__init__":
                continue
            module = importlib.import_module(f"app.evaluations.{eval_file.stem}")
            agent = getattr(module, "agent", None)
            cases = getattr(module, "cases", None)
            if agent is None or cases is None:
                raise InvalidEvalModule(
                    f"{eval_file} must define module-level `agent` and `cases`"
                )
            modules.append((agent, cases))

        async def _run_all() -> list[EvalResult]:
            results: list[EvalResult] = []
            for agent, cases in modules:
                results.extend(await run_evals(agent, executor, cases))
            return results

        return asyncio.run(_run_all())
