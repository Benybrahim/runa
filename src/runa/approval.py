"""approval.py: gates a tool call behind a human decision before it runs.

`requires_approval` on an Agent causes the Executor to pause a Run into
AWAITING_APPROVAL instead of executing a gated tool call (see
`runtime/executor.py`). Approving or denying is just another transition
through the same Run state machine, not a separate approval workflow
(manifesto §14).
"""

from runa.core import Run, ToolCall


class UnknownToolCall(Exception):
    """Raised when approving/denying a tool_call_id not found on the Run."""


def _find_tool_call(run: Run, tool_call_id: str) -> ToolCall:
    for tool_call in run.tool_calls:
        if tool_call.id == tool_call_id:
            return tool_call
    raise UnknownToolCall(tool_call_id)


def approve(run: Run, tool_call_id: str) -> None:
    """Approve a pending tool call and resume the Run.

    The tool itself doesn't run here: call `Executor.run()` again to
    continue driving the Run, which will now execute the approved call.
    """
    _find_tool_call(run, tool_call_id).approved = True
    run.resume()


def deny(run: Run, tool_call_id: str, *, reason: str = "") -> None:
    """Deny a pending tool call, failing the Run."""
    _find_tool_call(run, tool_call_id).approved = False
    run.resume()
    suffix = f": {reason}" if reason else ""
    run.fail(error=f"tool call {tool_call_id!r} denied{suffix}")
