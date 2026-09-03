"""cli/runs.py: `runa runs show/pending/approve/deny` — the Run store over argv.

Manifesto §11 asks that "what happened?" have an answer without adding
tracing code to every agent; §14 asks that human approval be part of the
runtime, not a Python-only API. Both are thin wiring over functions that
already exist — `default_run_store()`, `timeline()`, `approval.approve()`/
`deny()` — this module only exposes them to argv. Only useful once an app
configures a durable `RunStore` (see `config.py`), since the default is
in-memory and won't outlive the process that created the run.

Approving or denying here only moves the Run's status (see `approval.py`
docstring) — it does not execute the tool. Resuming actual execution is the
same as resuming any other paused Run: call the Executor again with the
Agent that produced it.
"""

from pathlib import Path

from runa.approval import approve, deny
from runa.cli._project import loaded_app
from runa.config import default_run_store
from runa.core import Run, RunStatus, ToolCall
from runa.observability import timeline
from runa.persistence import RunStore


class RunNotFound(Exception):
    """Raised when a `runa runs` command is given an id not in the RunStore."""


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


def _pending_tool_call(run: Run) -> ToolCall | None:
    """The tool call an AWAITING_APPROVAL Run is paused on, if any."""
    for tool_call in run.tool_calls:
        if tool_call.approved is None:
            return tool_call
    return None


def format_pending_runs(runs: list[Run]) -> str:
    pending = [
        (run, _pending_tool_call(run))
        for run in runs
        if run.status == RunStatus.AWAITING_APPROVAL
    ]
    lines = [
        f"{run.id}  {call.name}({call.arguments})  tool_call_id={call.id}"
        for run, call in pending
        if call is not None
    ]
    return "\n".join(lines) if lines else "no runs awaiting approval"


def list_pending_runs(*, root: Path) -> str:
    """Render every Run in the app's RunStore that's paused awaiting approval."""
    with loaded_app(root):
        runs = default_run_store().list()
    return format_pending_runs(runs)


def _get_run(store: RunStore, run_id: str) -> Run:
    run = store.get(run_id)
    if run is None:
        raise RunNotFound(f"no run found with id {run_id!r}")
    return run


def approve_run(run_id: str, tool_call_id: str, *, root: Path) -> str:
    """Approve a pending tool call and persist the Run's resumed status."""
    with loaded_app(root):
        store = default_run_store()
        run = _get_run(store, run_id)
        approve(run, tool_call_id)
        store.save(run)
    return f"approved {tool_call_id} on run {run_id} — now {run.status.value}"


def deny_run(run_id: str, tool_call_id: str, *, root: Path, reason: str = "") -> str:
    """Deny a pending tool call and persist the Run's failed status."""
    with loaded_app(root):
        store = default_run_store()
        run = _get_run(store, run_id)
        deny(run, tool_call_id, reason=reason)
        store.save(run)
    return f"denied {tool_call_id} on run {run_id} — now {run.status.value}"
