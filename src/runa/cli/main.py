"""cli/main.py: the `runa` command-line entry point.

`new` and `generate` are scaffolding: they write files following the app/
convention and never touch the runtime. `run`, `eval`, `test`, and `runs`
do touch it, but only by calling existing library functions
(`Runner.run_sync()`/`Runner.run()`, `agent.evaluate()`, `run_project_tests()`)
against the app in `cwd`; no logic lives here that doesn't already exist
elsewhere.
"""

import argparse
import sys
from pathlib import Path

from runa.cli._project import AppLoadError, NotARunaProject
from runa.cli.eval import InvalidEvalModule, run_project_evals
from runa.cli.generate import (
    AgentAlreadyExists,
    EvaluationAlreadyExists,
    ToolAlreadyExists,
    generate_agent,
    generate_evaluation,
    generate_tool,
)
from runa.cli.new import ProjectAlreadyExists, scaffold_project
from runa.cli.run import AgentNotFound, run_agent
from runa.cli.runs import (
    PendingApprovalNotFound,
    RunNotFound,
    approve_run,
    cancel_pending,
    deny_run,
    list_pending_runs,
    list_sessions,
    show_session,
)
from runa.cli.test import run_project_tests


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="runa", description="Scaffold, run, and evaluate Runa agents."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    new_parser = subparsers.add_parser("new", help="Scaffold a new Runa application")
    new_parser.add_argument("name")

    generate_parser = subparsers.add_parser(
        "generate", help="Generate scaffolding inside a Runa application"
    )
    generate_subparsers = generate_parser.add_subparsers(dest="kind", required=True)
    generate_subparsers.add_parser("agent", help="Generate a new Agent").add_argument("name")
    generate_subparsers.add_parser("tool", help="Generate a new @tool function").add_argument(
        "name"
    )
    generate_subparsers.add_parser(
        "evaluation", help="Generate a new app/evaluations/ case module"
    ).add_argument("name")

    run_parser = subparsers.add_parser("run", help="Run an Agent against an input")
    run_parser.add_argument("name", help="e.g. Support, or SupportAgent")
    run_parser.add_argument("input")
    run_parser.add_argument(
        "--session",
        default=None,
        help="conversation id to persist to/resume in runa.db; defaults to the Agent's class name",
    )

    subparsers.add_parser("eval", help="Run this app's app/evaluations/ cases")
    subparsers.add_parser("test", help="Run this app's app/tests/ test functions")

    runs_parser = subparsers.add_parser("runs", help="Inspect this app's sessions in runa.db")
    runs_subparsers = runs_parser.add_subparsers(dest="action", required=True)

    runs_subparsers.add_parser("list", help="List every session")
    runs_subparsers.add_parser("pending", help="List tool calls awaiting approval")

    runs_show_parser = runs_subparsers.add_parser("show", help="Show a session's history")
    runs_show_parser.add_argument("session_id")

    runs_approve_parser = runs_subparsers.add_parser(
        "approve", help="Approve a pending tool call and resume its run"
    )
    runs_approve_parser.add_argument("session_id")
    runs_approve_parser.add_argument("tool_call_id")

    runs_deny_parser = runs_subparsers.add_parser(
        "deny", help="Deny a pending tool call and resume its run"
    )
    runs_deny_parser.add_argument("session_id")
    runs_deny_parser.add_argument("tool_call_id")
    runs_deny_parser.add_argument("--reason", default="")

    runs_cancel_parser = runs_subparsers.add_parser(
        "cancel", help="Abandon a session's pending approval(s) without resuming"
    )
    runs_cancel_parser.add_argument("session_id")

    return parser


def main(argv: list[str] | None = None, *, cwd: Path | None = None) -> int:
    """Parse argv and dispatch.

    Operator-input errors (a mistyped session id or tool_call_id, running outside a Runa app
    directory) become a clean message on stderr and exit code 1 instead of a raw Python
    traceback. Anything else (a real bug, in Runa or in the app's own code) still propagates
    with its full traceback, since swallowing that would hide the thing a developer actually
    needs to see.
    """
    cwd = cwd or Path.cwd()
    args = _build_parser().parse_args(argv)

    try:
        return _dispatch(args, cwd)
    except ModuleNotFoundError as exc:
        if exc.name != "main":
            raise
        print(f"error: no main.py found in {cwd}, is this a Runa app?", file=sys.stderr)
        return 1
    except (
        RunNotFound,
        PendingApprovalNotFound,
        ProjectAlreadyExists,
        AgentAlreadyExists,
        AgentNotFound,
        ToolAlreadyExists,
        EvaluationAlreadyExists,
        NotARunaProject,
        InvalidEvalModule,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except AppLoadError as exc:
        print(
            f"error: failed to load {cwd / 'main.py'}: {exc}\n"
            "(run `python main.py` directly to see the full traceback)",
            file=sys.stderr,
        )
        return 1


def _dispatch(args: argparse.Namespace, cwd: Path) -> int:
    if args.command == "new":
        project_dir = scaffold_project(args.name, root=cwd)
        print(f"created {project_dir}")
        print(
            "\nnext steps:\n"
            f"  cd {project_dir.name}\n"
            "  put your OPENAI_API_KEY in .env   # or whichever model your agents use\n"
            "  runa generate agent MyAgent\n"
            "  runa run MyAgent '...'"
        )
        return 0

    if args.command == "generate" and args.kind == "agent":
        agent_file = generate_agent(args.name, root=cwd)
        print(f"created {agent_file}")
        class_name = args.name if args.name.endswith("Agent") else f"{args.name}Agent"
        print(
            "\nnext: declare its tools and instructions, then run it, "
            "either from the CLI:\n"
            f"  runa run {args.name} '...'\n"
            "or from your own code:\n"
            f"  from app.agents.{agent_file.stem} import {class_name}\n"
            f"  {class_name}().run_sync('...')"
        )
        return 0

    if args.command == "generate" and args.kind == "tool":
        tool_file = generate_tool(args.name, root=cwd)
        print(f"created {tool_file}")
        print(
            "\nnext: implement it, then declare it on an Agent, e.g.\n"
            f"  from app.tools.{tool_file.stem} import {tool_file.stem}\n"
            f"  tools = [{tool_file.stem}]"
        )
        return 0

    if args.command == "generate" and args.kind == "evaluation":
        eval_file = generate_evaluation(args.name, root=cwd)
        print(f"created {eval_file}")
        print(
            "\nnext: point `agent` at the Agent you want to evaluate and add "
            "Case(...) entries to `dataset`, then\n"
            "  runa eval"
        )
        return 0

    if args.command == "run":
        print(run_agent(args.name, args.input, root=cwd, session_id=args.session))
        return 0

    if args.command == "eval":
        reports = run_project_evals(cwd)
        for report in reports:
            print(report)
            print()
        total = sum(len(report.cases) for report in reports)
        failed = sum(len(report.failed) for report in reports)
        print(f"{total - failed}/{total} passed")
        return 1 if failed else 0

    if args.command == "test":
        results = run_project_tests(cwd)
        for result in results:
            status = "PASS" if result.passed else f"FAIL: {result.error}"
            print(f"{result.name}: {status}")
        failed = sum(1 for result in results if not result.passed)
        print(f"\n{len(results) - failed}/{len(results)} passed")
        return 1 if failed else 0

    if args.action == "list":
        print(list_sessions(root=cwd))
        return 0

    if args.action == "show":
        print(show_session(args.session_id, root=cwd))
        return 0

    if args.action == "pending":
        print(list_pending_runs(root=cwd))
        return 0

    if args.action == "approve":
        print(approve_run(args.session_id, args.tool_call_id, root=cwd))
        return 0

    if args.action == "deny":
        print(deny_run(args.session_id, args.tool_call_id, root=cwd, reason=args.reason))
        return 0

    print(cancel_pending(args.session_id, root=cwd))
    return 0
