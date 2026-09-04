"""Conversation: state and history that persist across separate Runs.

Manifesto §8 draws a line between Run state (one execution), Conversation
state (across interactions), and Application state (the domain). A `Run`
is still the unit of computation — a `Conversation` doesn't replace it or
run anything itself. It's the thing a caller holds onto between calls to
`Agent.run(..., conversation=...)` so the next Run can pick up where the
last one left off.

Concurrency: a Conversation is explicitly meant to be held across separate
Runs (unlike a `Run`, which one Executor drives at a time — see
`ThreadQueue`), but that does not make two Runs *concurrently* against the
same Conversation safe. `record()` is locked only to keep one `record()`
call from tearing another's write — a Conversation given to two Runs that
overlap in time still loses whichever Run finishes `record()` first: each
Run seeds its history from the Conversation at the moment it starts, and
the later `record()` call replaces `.messages` wholesale, with no awareness
of the other Run's turn. There is no merge — building one would mean
guessing how to interleave two independent exchanges, which is an
application decision, not one Runa can make for it. Give each concurrent
Run its own Conversation and merge deliberately, or sequence Runs against a
shared Conversation (finish one — including `record()` — before starting
the next).

Growth: `record()` never truncates — `.messages` grows by one Run's worth
of turns every time, indefinitely. `seed_run()` (`runtime/_shared.py`)
sends all of it to the model on every subsequent Run, so a long-lived
Conversation eventually produces a Provider call that exceeds the model's
context window; that fails the Run cleanly (`RunStatus.FAILED` with the
Provider's error), not a crash, but it does mean the conversation is now
stuck failing every future Run against it. Runa doesn't truncate or
summarize on the application's behalf — manifesto §6 draws the same line
against turning this into an agent-specific memory system it draws for
Run/Conversation/Application state generally. `.messages` is a plain list;
trim it yourself between Runs (e.g. `conversation.messages = conversation.
messages[-N:]`) or fold older turns into `conversation.state` as a summary
if losing raw history is unacceptable.
"""

import threading
import uuid
from dataclasses import dataclass, field

from runa.core.message import Message, Role
from runa.core.run import Run
from runa.core.state import ConversationState


@dataclass
class Conversation:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    state: ConversationState = field(default_factory=ConversationState)
    messages: list[Message] = field(default_factory=list)

    def __post_init__(self) -> None:
        # Not a dataclass field: a lock can't be meaningfully copied or
        # compared, and conversation_from_dict() reconstructs a Conversation
        # through this same __init__/__post_init__ path, so every instance
        # — freshly created or deserialized — gets its own.
        self._lock = threading.Lock()

    def record(self, run: Run) -> None:
        """Fold a Run's messages back into history once it's terminal.

        The system prompt is re-derived from `Agent.instructions` on every
        Run, so it's excluded here rather than duplicated on the next turn.

        Locked so that two Runs finishing at nearly the same moment can't
        interleave their writes into a corrupted `.messages` — see the
        class docstring for what this lock does *not* protect against.
        """
        messages = [m for m in run.messages if m.role != Role.SYSTEM]
        with self._lock:
            self.messages = messages
