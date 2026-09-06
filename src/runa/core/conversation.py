"""Conversation: state and history that persist across separate Runs.

Manifesto §8 draws a line between Run state (one execution), Conversation
state (across interactions), and Domain state (the application's domain). A
`Run` is still the unit of computation; a `Conversation` doesn't replace it or
run anything itself. It's the thing a caller holds onto between calls to
`Agent.run(..., conversation=...)` so the next Run can pick up where the
last one left off.

Ownership boundary: `Run.messages` is the transcript this Run's own
computation produced and consumed (its system prompt, its input, and its
own assistant/tool turns). `Conversation.messages` is the durable,
cross-Run history; it is the only thing that spans Runs. A `Run` never
holds a live `Conversation` reference (only a `conversation_id`, for
lineage), and it never copies the Conversation's history into its own
`.messages`: the full model context for a call is assembled as a
projection at call time (`runtime._shared.model_context`), combining
`Conversation.messages` with the calling Run's own messages, rather than
stored as a merged blob on either object. See RUNA.md: "Model context is a
projection... not a stored object."

Concurrency: a Conversation is explicitly meant to be held across separate
Runs (unlike a `Run`, which one Executor drives at a time, see
`ThreadQueue`). `record()` is locked so that two Runs finishing at nearly
the same moment append rather than tear or clobber each other's turns: no
Run's contribution to `.messages` is lost. What the lock does not resolve
is temporal consistency across concurrent Runs: each Run's own model calls
only ever see `.messages` as it stood at the moment of that call, so two
Runs racing against the same Conversation may each answer with no
awareness of the other's turn, and whichever finishes `record()` last
simply appends after, regardless of which Run was "logically" first.
There is no merge into one coherent narrative: building one would mean
guessing how to interleave two independent exchanges, which is an
application decision, not one Runa can make for it. Give each concurrent
Run its own Conversation and merge deliberately, or sequence Runs against a
shared Conversation (finish one, including `record()`, before starting
the next) if turn order matters.

Growth: `record()` never truncates; it appends. `.messages` grows by one
Run's worth of turns every time, indefinitely. `model_context()` sends all
of it to the model on every subsequent Run, so a long-lived Conversation
eventually produces a Provider call that exceeds the model's context
window; that fails the Run cleanly (`RunStatus.FAILED` with the Provider's
error), not a crash, but it does mean the conversation is now stuck
failing every future Run against it. Runa doesn't truncate or summarize on
the application's behalf; manifesto §6 draws the same line against turning
this into an agent-specific memory system it draws for
Run/Conversation/Domain state generally. `.messages` is a plain list; trim
it yourself between Runs (e.g. `conversation.messages = conversation.
messages[-N:]`) or fold older turns into `conversation.state` as a summary
if losing raw history is unacceptable.
"""

import threading
import uuid
from dataclasses import dataclass, field

from runa.core.message import Message, Role
from runa.core.state import ConversationState


@dataclass
class Conversation:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    state: ConversationState = field(default_factory=ConversationState)
    messages: list[Message] = field(default_factory=list)

    def __post_init__(self) -> None:
        # Not a dataclass field: a lock can't be meaningfully copied or
        # compared, and conversation_from_dict() reconstructs a Conversation
        # through this same __init__/__post_init__ path, so every instance,
        # freshly created or deserialized, gets its own.
        self._lock = threading.Lock()

    def record(self, messages: list[Message]) -> None:
        """Append messages to this conversation's durable history.

        SYSTEM messages are excluded because the system prompt is
        re-derived from `Agent.instructions` on every Run, so it would
        otherwise be duplicated on the next turn.

        Locked so that two callers recording at nearly the same moment each
        contribute one whole, uninterleaved batch. See the class docstring
        for what this lock does *not* protect against.
        """
        messages = [m for m in messages if m.role != Role.SYSTEM]
        with self._lock:
            self.messages += messages
