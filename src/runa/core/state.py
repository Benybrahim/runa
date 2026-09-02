"""Explicit, scoped state containers.

Runa distinguishes Run state, Conversation state, and Application state
rather than hiding them behind one universal memory abstraction. Application
state is intentionally not modeled here — it belongs to the developer's own
domain objects (Customer, Order, ResearchProject, ...).
"""

from typing import Any


class _AttrDict(dict):
    """A dict that also supports attribute access, e.g. state.plan."""

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
    """State scoped to a single Run's execution."""


class ConversationState(_AttrDict):
    """State that persists across interactions in a conversation."""
