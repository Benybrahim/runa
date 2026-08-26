from dataclasses import dataclass


@dataclass(frozen=True)
class Run:
    """A single execution of an agent."""

    id: str
    input: str
    output: str
    model: str
    status: str
