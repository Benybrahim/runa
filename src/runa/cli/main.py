"""cli/main.py: the `runa` command-line entry point.

`new` and `generate` are scaffolding (manifesto §2, §9) — they write files
following the app/ convention and never touch the runtime. `eval` and
`runs show` do touch it, but only by calling existing library functions
(`run_evals()`, `timeline()`) against the app in `cwd` — no logic lives here
that doesn't already exist elsewhere (manifesto §11, §12).
"""

import argparse
from pathlib import Path

from runa.cli.eval import run_project_evals
from runa.cli.generate import generate_agent
from runa.cli.new import scaffold_project
from runa.cli.runs import show_run


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="runa")
    subparsers = parser.add_subparsers(dest="command", required=True)

    new_parser = subparsers.add_parser("new", help="Scaffold a new Runa application")
    new_parser.add_argument("name")

    generate_parser = subparsers.add_parser(
        "generate", help="Generate scaffolding inside a Runa application"
    )
    generate_subparsers = generate_parser.add_subparsers(dest="kind", required=True)
    generate_agent_parser = generate_subparsers.add_parser(
        "agent", help="Generate a new Agent"
    )
    generate_agent_parser.add_argument("name")

    subparsers.add_parser("eval", help="Run this app's app/evaluations/ cases")

    runs_parser = subparsers.add_parser("runs", help="Inspect this app's Runs")
    runs_subparsers = runs_parser.add_subparsers(dest="action", required=True)
    runs_show_parser = runs_subparsers.add_parser("show", help="Show a Run's timeline")
    runs_show_parser.add_argument("run_id")

    return parser


def main(argv: list[str] | None = None, *, cwd: Path | None = None) -> int:
    cwd = cwd or Path.cwd()
    args = _build_parser().parse_args(argv)

    if args.command == "new":
        project_dir = scaffold_project(args.name, root=cwd)
        print(f"created {project_dir}")
        return 0

    if args.command == "generate":
        agent_file = generate_agent(args.name, root=cwd)
        print(f"created {agent_file}")
        return 0

    if args.command == "eval":
        results = run_project_evals(cwd)
        for result in results:
            status = "PASS" if result.passed else f"FAIL: {result.error}"
            print(f"{result.case.name}: {status}")
        failed = sum(1 for result in results if not result.passed)
        print(f"\n{len(results) - failed}/{len(results)} passed")
        return 1 if failed else 0

    print(show_run(args.run_id, root=cwd))
    return 0
