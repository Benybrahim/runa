"""Run: the primary unit of computation in Runa."""

import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from runa.core.artifact import Artifact
from runa.core.context import Context
from runa.core.event import Event, EventType
from runa.core.message import Message, ToolCall
from runa.core.state import RunState

if TYPE_CHECKING:
    # Only Executor._seed reads Run.conversation, and Conversation.record
    # takes a Run; an unconditional import here would cycle.
    from runa.core.conversation import Conversation


class RunStatus(StrEnum):
    CREATED = "created"
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


_TRANSITIONS: dict[RunStatus, set[RunStatus]] = {
    RunStatus.CREATED: {RunStatus.QUEUED, RunStatus.RUNNING, RunStatus.CANCELLED},
    RunStatus.QUEUED: {RunStatus.RUNNING, RunStatus.CANCELLED},
    RunStatus.RUNNING: {
        RunStatus.PAUSED,
        RunStatus.AWAITING_APPROVAL,
        RunStatus.COMPLETED,
        RunStatus.FAILED,
        RunStatus.CANCELLED,
    },
    RunStatus.PAUSED: {RunStatus.RUNNING, RunStatus.CANCELLED},
    RunStatus.AWAITING_APPROVAL: {RunStatus.RUNNING, RunStatus.CANCELLED},
    RunStatus.COMPLETED: set(),
    RunStatus.FAILED: set(),
    RunStatus.CANCELLED: set(),
}


class IllegalTransition(Exception):
    """Raised when a Run is asked to move to a status it cannot reach."""


class RunAlreadyDriving(Exception):
    """Raised when a second Executor tries to drive a Run already in flight.

    See `Run.begin_driving()`.
    """


@dataclass
class Run:
    input: Any
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    agent_name: str | None = None
    active_agent_name: str | None = None
    agent_version: str | None = None
    parent_run_id: str | None = None
    context: Context = field(default_factory=Context)
    state: RunState = field(default_factory=RunState)
    messages: list[Message] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)
    tool_calls: list[ToolCall] = field(default_factory=list)
    artifacts: list[Artifact] = field(default_factory=list)
    conversation: "Conversation | None" = None
    result: Any = None
    error: str | None = None
    status: RunStatus = RunStatus.CREATED
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    cancel_requested: bool = False

    def __post_init__(self) -> None:
        # Not a dataclass field: a lock can't be meaningfully copied,
        # compared, or serialized, and run_from_dict() reconstructs a Run
        # through this same __init__/__post_init__ path, so every instance
        # (freshly created or deserialized) gets its own.
        self._drive_lock = threading.Lock()
        self._driving = False

    def begin_driving(self) -> None:
        """Claim exclusive execution of this Run object. Called by
        Executor/AsyncExecutor at the start of `run()`.

        A Run has no concurrency control of its own over `add_message`/
        `emit`/status transitions: two Executors advancing the same Run
        object at once would otherwise interleave their steps with no
        error at all, silently duplicating model calls and tool side
        effects instead of failing loudly. Raises `RunAlreadyDriving` if
        another Executor is already driving this Run.

        This only catches this one framework entry point being called
        twice on the same in-memory object, not two separate `Run`
        objects loaded for the same persisted `run_id` (that hazard is a
        `RunStore`/application concern; see also `ThreadQueue`'s docstring,
        which already warns against reading a queued Run from another
        thread, and `Conversation`'s docstring for the analogous boundary
        there).
        """
        with self._drive_lock:
            if self._driving:
                raise RunAlreadyDriving(
                    f"Run {self.id} is already being driven by another "
                    "Executor: two Executors cannot advance the same Run "
                    "object concurrently"
                )
            self._driving = True

    def end_driving(self) -> None:
        """Release the claim `begin_driving()` took. Always call this in a
        `finally`, so a Run stays drivable again after its Executor call
        returns, including when that call raised."""
        with self._drive_lock:
            self._driving = False

    def emit(self, event_type: EventType, **data: Any) -> Event:
        event = Event(type=event_type, data=data)
        self.events.append(event)
        return event

    def add_message(self, message: Message) -> None:
        self.messages.append(message)
        self.tool_calls.extend(message.tool_calls)

    def add_artifact(self, artifact: Artifact) -> None:
        self.artifacts.append(artifact)
        self.emit(EventType.ARTIFACT_CREATED, artifact_id=artifact.id)

    def transition_to(
        self, status: RunStatus, event_type: EventType, **event_data: Any
    ) -> None:
        allowed = _TRANSITIONS[self.status]
        if status not in allowed:
            raise IllegalTransition(f"cannot move Run from {self.status} to {status}")
        self.status = status
        self.emit(event_type, **event_data)

    def queue(self) -> None:
        self.transition_to(RunStatus.QUEUED, EventType.RUN_QUEUED)

    def start(self) -> None:
        self.transition_to(RunStatus.RUNNING, EventType.RUN_STARTED)

    def pause(self) -> None:
        self.transition_to(RunStatus.PAUSED, EventType.RUN_PAUSED)

    def require_approval(self, tool_call_id: str) -> None:
        self.transition_to(
            RunStatus.AWAITING_APPROVAL,
            EventType.APPROVAL_REQUIRED,
            tool_call_id=tool_call_id,
        )

    def resume(self) -> None:
        self.transition_to(RunStatus.RUNNING, EventType.RUN_RESUMED)

    def complete(self, result: Any = None) -> None:
        self.result = result
        self.transition_to(RunStatus.COMPLETED, EventType.RUN_COMPLETED)

    def fail(self, error: str) -> None:
        self.error = error
        self.transition_to(RunStatus.FAILED, EventType.RUN_FAILED, error=error)

    def cancel(self) -> None:
        self.transition_to(RunStatus.CANCELLED, EventType.RUN_CANCELLED)

    def request_cancel(self) -> None:
        """Ask a Run being driven elsewhere to stop at its next checkpoint.

        Only `Run.status`/`Run.events` mutation is owned by whichever thread
        is actively driving the Run through `Executor.run()`: calling
        `cancel()` directly from another thread would race that loop and can
        raise `IllegalTransition` if it wins the race after the Run has
        already reached a terminal status. Setting this flag is safe from
        any thread at any time; `Executor.run()` checks it once per step and
        performs the actual `cancel()` transition itself, on its own thread,
        the same way `max_steps` already bounds the loop. A Run that isn't
        currently being driven (CREATED/QUEUED/PAUSED/AWAITING_APPROVAL,
        e.g. one sitting in a RunStore) has no owning thread to race, so
        `cancel()` there works directly; see `runa runs cancel`.
        """
        self.cancel_requested = True

    @property
    def is_terminal(self) -> bool:
        return not _TRANSITIONS[self.status]

    @property
    def completed(self) -> bool:
        return self.status == RunStatus.COMPLETED

    @property
    def usage(self) -> dict[str, int]:
        """Token usage summed across every model call this Run has made.

        Each `Message.usage` is already normalized to `{"input_tokens",
        "output_tokens"}` by the Provider that produced it (architecture.md
        §10); this just adds them up so an application doesn't need to walk
        `run.messages` itself to answer "what did this Run cost?" A Message
        with no usage (not a model response, or a provider that didn't
        report it) contributes nothing. Always both keys, zeroed rather than
        omitted, for a Run that hasn't called a model yet.
        """
        totals = {"input_tokens": 0, "output_tokens": 0}
        for message in self.messages:
            if message.usage is None:
                continue
            for key in totals:
                totals[key] += message.usage.get(key, 0)
        return totals
