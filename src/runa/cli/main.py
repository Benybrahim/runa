"""cli/main.py: the `runa` command-line entry point.

`new` and `generate` are scaffolding (manifesto §2, §9) — they write files
following the app/ convention and never touch the runtime. `eval`, `test`,
and `runs` do touch it, but only by calling existing library functions
(`run_project_evals()`, `run_project_tests()`, `timeline()`,
`approval.approve()`/`deny()`, `Run.cancel()`) against the app in `cwd` — no
logic lives here that doesn't already exist elsewhere (manifesto §11, §12,
§14).
"""

import argparse
from pathlib import Path

from runa.cli.eval import run_project_evals
from runa.cli.generate import generate_agent
from runa.cli.new import scaffold_project
from runa.cli.runs import (
    approve_run,
    cancel_run,
    deny_run,
    list_pending_runs,
    list_runs,
    show_run,
)
from runa.cli.test import run_project_tests


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
    subparsers.add_parser("test", help="Run this app's app/tests/ test functions")

    runs_parser = subparsers.add_parser("runs", help="Inspect this app's Runs")
    runs_subparsers = runs_parser.add_subparsers(dest="action", required=True)

    runs_show_parser = runs_subparsers.add_parser("show", help="Show a Run's timeline")
    runs_show_parser.add_argument("run_id")

    runs_list_parser = runs_subparsers.add_parser(
        "list",
        help="List Runs, optionally filtered by status/since/agent-name/parent-run-id",
    )
    runs_list_parser.add_argument(
        "--status", default=None, help="e.g. completed, failed, awaiting_approval"
    )
    runs_list_parser.add_argument(
        "--since", default=None, help="ISO 8601 timestamp; only Runs at or after it"
    )
    runs_list_parser.add_argument(
        "--agent-name", default=None, help="e.g. ResearchAgent — see Agent.name"
    )
    runs_list_parser.add_argument(
        "--parent-run-id", default=None, help="only Runs delegated from this Run"
    )

    runs_subparsers.add_parser("pending", help="List Runs paused awaiting approval")

    runs_approve_parser = runs_subparsers.add_parser(
        "approve", help="Approve a pending tool call and resume the Run"
    )
    runs_approve_parser.add_argument("run_id")
    runs_approve_parser.add_argument("tool_call_id")

    runs_deny_parser = runs_subparsers.add_parser(
        "deny", help="Deny a pending tool call and fail the Run"
    )
    runs_deny_parser.add_argument("run_id")
    runs_deny_parser.add_argument("tool_call_id")
    runs_deny_parser.add_argument("--reason", default="")

    runs_cancel_parser = runs_subparsers.add_parser(
        "cancel", help="Cancel a saved Run that isn't currently being driven"
    )
    runs_cancel_parser.add_argument("run_id")

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

    if args.command == "test":
        results = run_project_tests(cwd)
        for result in results:
            status = "PASS" if result.passed else f"FAIL: {result.error}"
            print(f"{result.name}: {status}")
        failed = sum(1 for result in results if not result.passed)
        print(f"\n{len(results) - failed}/{len(results)} passed")
        return 1 if failed else 0

    if args.action == "show":
        print(show_run(args.run_id, root=cwd))
        return 0

    if args.action == "list":
        print(
            list_runs(
                root=cwd,
                status=args.status,
                since=args.since,
                agent_name=args.agent_name,
                parent_run_id=args.parent_run_id,
            )
        )
        return 0

    if args.action == "pending":
        print(list_pending_runs(root=cwd))
        return 0

    if args.action == "approve":
        print(approve_run(args.run_id, args.tool_call_id, root=cwd))
        return 0

    if args.action == "deny":
        print(deny_run(args.run_id, args.tool_call_id, root=cwd, reason=args.reason))
        return 0

    print(cancel_run(args.run_id, root=cwd))
    return 0
