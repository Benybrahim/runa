from dataclasses import dataclass


@dataclass(frozen=True)
class Run:
    """A single execution of an agent."""

    id: str
    output: str
