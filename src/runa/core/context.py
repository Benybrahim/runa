"""Context: the information handed to an Agent to make a decision.

Distinct from State (see state.py): State is owned by the application and
the runtime; Context is what the Agent is given (architecture.md §2, §16).
Application code assembles it deliberately, the same way it populates Run
state, and can inspect it afterward to see what was available to the Agent
for a given Run.
"""

from runa.core.state import _AttrDict


class Context(_AttrDict):
    """Information assembled for an Agent's decision-making, attached to a Run."""
