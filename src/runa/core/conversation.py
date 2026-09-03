"""Conversation: state and history that persist across separate Runs.

Manifesto §8 draws a line between Run state (one execution), Conversation
state (across interactions), and Application state (the domain). A `Run`
is still the unit of computation — a `Conversation` doesn't replace it or
run anything itself. It's the thing a caller holds onto between calls to
`Agent.run(..., conversation=...)` so the next Run can pick up where the
last one left off.
"""

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

    def record(self, run: Run) -> None:
        """Fold a Run's messages back into history once it's terminal.

        The system prompt is re-derived from `Agent.instructions` on every
        Run, so it's excluded here rather than duplicated on the next turn.
        """
        self.messages = [m for m in run.messages if m.role != Role.SYSTEM]
