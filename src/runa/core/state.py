"""Runtime state containers with explicit lifetimes.

Runa models state owned by its runtime:

- RunState: belongs to one Run.
- ConversationState: spans multiple Runs.

Domain state is intentionally not modeled here. It belongs to the
developer's own domain objects (Customer, Order, ResearchProject, ...).

State has a lifetime.
"""

from typing import Any


class _AttrDict(dict):
    """A dict that also supports attribute access."""

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name: str, value: Any) -> None:
        self[name] = value

    def __delattr__(self, name: str) -> None:
        try:
            del self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


class RunState(_AttrDict):
    """State owned by a single Run."""


class ConversationState(_AttrDict):
    """State owned by a Conversation and shared across its Runs."""