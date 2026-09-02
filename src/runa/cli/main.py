"""cli/main.py: the `runa` command-line entry point.

Scaffolding only (manifesto §2, §9) — `new` and `generate` write files
following the app/ convention; nothing here touches the runtime.
"""

import argparse
from pathlib import Path

from runa.cli.generate import generate_agent
from runa.cli.new import scaffold_project


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

    return parser


def main(argv: list[str] | None = None, *, cwd: Path | None = None) -> int:
    cwd = cwd or Path.cwd()
    args = _build_parser().parse_args(argv)

    if args.command == "new":
        project_dir = scaffold_project(args.name, root=cwd)
        print(f"created {project_dir}")
        return 0

    agent_file = generate_agent(args.name, root=cwd)
    print(f"created {agent_file}")
    return 0
