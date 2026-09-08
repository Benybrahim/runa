"""cli/run.py: `runa run` and `runa chat`, invoke an Agent from argv.

Calls `Runner.run_sync()` directly rather than `Agent.run_sync()`: the CLI
needs the full `RunResult` (to detect `interruptions` and persist them, see
`cli/_approvals.py`), while `Agent.run_sync()` only returns the final
output string. Conversation history persists across invocations by
default, via a `SQLiteSession` keyed by the Agent's class name over the
app's `runa.db` (the same file `runa runs` reads).
"""

import importlib
import inspect
import json
from collections.abc import Iterator
from pathlib import Path

from agents import Runner

from runa.agent import _RUN_CONFIG, Agent, _default_hooks
from runa.cli import _approvals
from runa.cli._project import NotARunaProject, loaded_app
from runa.session import SQLiteSession


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


def _iter_agent_classes(agents_dir: Path) -> Iterator[type[Agent]]:
    for agent_file in sorted(agents_dir.glob("*.py")):
        if agent_file.stem == "__init__":
            continue
        module = importlib.import_module(f"app.agents.{agent_file.stem}")
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if issubclass(obj, Agent) and obj is not Agent and obj.__module__ == module.__name__:
                yield obj


def find_agent_class(name: str, *, agents_dir: Path) -> type[Agent]:
    """Find the Agent subclass named `name` under `agents_dir`.

    Matches either the exact class name or, following `runa generate agent`'s own convention,
    `name` with an `Agent` suffix appended, so `runa run Support ...` finds `SupportAgent`
    without spelling out the suffix.
    """
    candidates = {name, name if name.endswith("Agent") else f"{name}Agent"}
    for agent_cls in _iter_agent_classes(agents_dir):
        if agent_cls.__name__ in candidates:
            return agent_cls
    raise AgentNotFound(f"no Agent named {name!r} found under {agents_dir}")


def run_agent(name: str, input: str, *, root: Path, session_id: str | None = None) -> str:
    """Run the named Agent against `input` over its persistent session, and format the result.

    `session_id` defaults to the Agent's class name, so repeated `runa run <name> ...` calls
    continue the same conversation; pass a different id to keep several conversations with the
    same Agent apart. If the run pauses on a tool call awaiting approval, its `RunState` is
    saved to `runa.db` (see `cli/_approvals.py`) instead of returning a final answer.
    """
    agents_dir = _require_agents_dir(root)
    db_path = root / "runa.db"

    with loaded_app(root):
        agent_cls = find_agent_class(name, agents_dir=agents_dir)
        resolved_session_id = session_id or agent_cls.__name__
        session = SQLiteSession(resolved_session_id, db_path=db_path)
        result = Runner.run_sync(
            agent_cls(), input, hooks=_default_hooks(), run_config=_RUN_CONFIG, session=session
        )

    if result.interruptions:
        _approvals.save_pending(
            db_path,
            session_id=resolved_session_id,
            agent_class_name=agent_cls.__name__,
            interruptions=result.interruptions,
            state_json=json.dumps(result.to_state().to_json()),
        )
        lines = [f"session {resolved_session_id!r} is awaiting approval:"]
        for item in result.interruptions:
            lines.append(f"  {item.name}({item.arguments})  tool_call_id={item.call_id}")
        lines.append(f"\napprove with: runa runs approve {resolved_session_id} <tool_call_id>")
        return "\n".join(lines)

    return str(result.final_output)


def run_agent_repl(name: str, *, root: Path, session_id: str | None = None) -> None:
    """Chat with the named Agent in a loop, over one persistent session.

    Unlike `run_agent()`, the app is loaded and the Agent instantiated once for the whole
    session, so turns share the in-process object instead of round-tripping through `runa.db`
    on every call. A pending approval is resolved right here by prompting the operator, rather
    than parking it for a separate `runa runs approve`/`deny` invocation.
    """
    agents_dir = _require_agents_dir(root)
    db_path = root / "runa.db"

    with loaded_app(root):
        agent_cls = find_agent_class(name, agents_dir=agents_dir)
        agent = agent_cls()
        resolved_session_id = session_id or agent_cls.__name__
        session = SQLiteSession(resolved_session_id, db_path=db_path)

        print(f"chatting with {agent_cls.__name__} (session {resolved_session_id!r})")
        print("type 'exit' or Ctrl-D to quit\n")

        while True:
            try:
                user_input = input("> ").strip()
            except EOFError, KeyboardInterrupt:
                print()
                return
            if not user_input:
                continue
            if user_input in {"exit", "quit"}:
                return

            result = Runner.run_sync(
                agent, user_input, hooks=_default_hooks(), run_config=_RUN_CONFIG, session=session
            )

            while result.interruptions:
                state = result.to_state()
                for item in result.interruptions:
                    answer = input(f"approve {item.name}({item.arguments})? [y/N] ").strip().lower()
                    if answer in {"y", "yes"}:
                        state.approve(item)
                    else:
                        state.reject(item)
                result = Runner.run_sync(
                    agent, state, hooks=_default_hooks(), run_config=_RUN_CONFIG, session=session
                )

            print(result.final_output)
