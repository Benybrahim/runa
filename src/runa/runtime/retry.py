"""RetryStrategy: retries a failing tool call before giving up on the run.

A second concrete `Strategy`, not a flag on `DefaultStrategy`: "reach for a
custom Strategy only when the loop's shape itself must change" (see
`strategy.py`), and retrying is exactly that: `DefaultStrategy` fails the
run on the first tool error, `RetryStrategy` re-attempts the same call in
place first.
"""

from runa.core import Run
from runa.runtime.strategy import (
    Action,
    CallModel,
    CallTool,
    Complete,
    Fail,
    last_assistant_message,
)


class RetryStrategy:
    """Like DefaultStrategy, but retries a failed tool call before failing.

    Retries happen without a model round-trip (same tool, same arguments),
    which suits transient failures (a flaky call, a rate limit) rather than
    errors caused by bad arguments, which would just fail the same way every
    time. `max_retries` is retries *after* the first attempt, so a tool call
    gets `max_retries + 1` attempts in total before the run fails.

    A failed call is only retried when its Tool declared `idempotent = True`.
    An error leaves the call's effect UNKNOWN (see `EffectStatus`); there's
    no way to tell whether its side effect already happened, so repeating a
    non-idempotent call risks duplicating that effect (a second charge, a
    second email). Such a call fails on its very first error instead of
    being retried, regardless of `max_retries` (architecture.md §13:
    "retries must not blindly repeat side effects").
    """

    def __init__(self, max_retries: int = 3) -> None:
        self.max_retries = max_retries

    def step(self, run: Run) -> Action:
        last_assistant = last_assistant_message(run)
        if last_assistant is None:
            return CallModel()

        pending = next(
            (tc for tc in last_assistant.tool_calls if not tc.succeeded), None
        )
        if pending is not None:
            if pending.error is not None:
                if not pending.idempotent or pending.attempts > self.max_retries:
                    return Fail(error=pending.error)
            return CallTool(tool_call=pending)

        if run.messages[-1] is last_assistant:
            return Complete(result=last_assistant.content)

        return CallModel()
