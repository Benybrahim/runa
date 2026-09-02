"""RetryStrategy: retries a failing tool call before giving up on the run.

A second concrete `Strategy`, not a flag on `DefaultStrategy` — "reach for a
custom Strategy only when the loop's shape itself must change" (see
`strategy.py`), and retrying is exactly that: `DefaultStrategy` fails the
run on the first tool error, `RetryStrategy` re-attempts the same call in
place first.
"""

from runa.core import Role, Run
from runa.runtime.strategy import Action, CallModel, CallTool, Complete, Fail


class RetryStrategy:
    """Like DefaultStrategy, but retries a failed tool call before failing.

    Retries happen without a model round-trip — same tool, same arguments —
    which suits transient failures (a flaky call, a rate limit) rather than
    errors caused by bad arguments, which would just fail the same way every
    time. `max_retries` is retries *after* the first attempt, so a tool call
    gets `max_retries + 1` attempts in total before the run fails.
    """

    def __init__(self, max_retries: int = 3) -> None:
        self.max_retries = max_retries

    def step(self, run: Run) -> Action:
        if not run.messages:
            return CallModel()

        last = run.messages[-1]

        if last.role != Role.ASSISTANT:
            return CallModel()

        pending = next((tc for tc in last.tool_calls if not tc.completed), None)
        if pending is not None:
            if pending.error is not None and pending.attempts > self.max_retries:
                return Fail(error=pending.error)
            return CallTool(tool_call=pending)

        return Complete(result=last.content)
