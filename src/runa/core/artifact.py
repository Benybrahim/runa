"""Artifact: first-class, non-text-only output produced during a Run.

A Tool's `call()` may return an Artifact instead of a plain value: the
Executor recognizes it by type (manifesto §2: "types are configuration")
and records it on the Run automatically (see `runtime/executor.py`), so
"agents create artifacts" (manifesto §10) is a normal consequence of a tool
running, not a separate API a developer has to remember to call.
`summary()` is what the model sees as that tool call's result; override it
on a custom Artifact subclass to control that text.
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass
class Artifact:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def summary(self) -> str:
        """Plain-text form fed back to the model as the tool call's result."""
        return f"artifact created: {self.id}"


@dataclass(kw_only=True)
class TextArtifact(Artifact):
    text: str

    def summary(self) -> str:
        return self.text


@dataclass(kw_only=True)
class DataArtifact(Artifact):
    data: dict = field(default_factory=dict)

    def summary(self) -> str:
        return str(self.data)


@dataclass(kw_only=True)
class FileArtifact(Artifact):
    path: str
    mime_type: str | None = None

    def summary(self) -> str:
        return f"file created: {self.path}"


@dataclass(kw_only=True)
class CitationSetArtifact(Artifact):
    citations: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return "\n".join(self.citations)


@dataclass(kw_only=True)
class PlanArtifact(Artifact):
    steps: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return "\n".join(f"{i}. {step}" for i, step in enumerate(self.steps, start=1))


@dataclass(kw_only=True)
class ActionArtifact(Artifact):
    name: str
    parameters: dict = field(default_factory=dict)

    def summary(self) -> str:
        return f"{self.name}({self.parameters})"
