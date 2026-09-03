"""RunStore: makes a Run's status and history durable across process steps.

This is what makes pause/resume and background execution possible at all —
a paused or awaiting-approval Run has to live somewhere between the request
that created it and the request that resumes it.
"""

from datetime import datetime
from typing import Protocol

from runa.core import Run, RunStatus


class RunStore(Protocol):
    def save(self, run: Run) -> None: ...
    def get(self, run_id: str) -> Run | None: ...
    def list(
        self,
        *,
        status: RunStatus | None = None,
        since: datetime | None = None,
        agent_id: str | None = None,
    ) -> list[Run]: ...


class InMemoryRunStore:
    """Default RunStore: keeps Runs in a process-local dict.

    This is the development default (manifesto: real backends are swapped
    in via configuration, not code changes) — nothing here survives a
    process restart.
    """

    def __init__(self) -> None:
        self._runs: dict[str, Run] = {}

    def save(self, run: Run) -> None:
        self._runs[run.id] = run

    def get(self, run_id: str) -> Run | None:
        return self._runs.get(run_id)

    def list(
        self,
        *,
        status: RunStatus | None = None,
        since: datetime | None = None,
        agent_id: str | None = None,
    ) -> list[Run]:
        return [
            run
            for run in self._runs.values()
            if (status is None or run.status == status)
            and (since is None or run.created_at >= since)
            and (agent_id is None or run.agent_id == agent_id)
        ]
