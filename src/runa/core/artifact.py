"""Artifact: first-class, non-text-only output produced during a Run."""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass
class Artifact:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(kw_only=True)
class TextArtifact(Artifact):
    text: str


@dataclass(kw_only=True)
class DataArtifact(Artifact):
    data: dict = field(default_factory=dict)


@dataclass(kw_only=True)
class FileArtifact(Artifact):
    path: str
    mime_type: str | None = None


@dataclass(kw_only=True)
class CitationSetArtifact(Artifact):
    citations: list[str] = field(default_factory=list)


@dataclass(kw_only=True)
class PlanArtifact(Artifact):
    steps: list[str] = field(default_factory=list)


@dataclass(kw_only=True)
class ActionArtifact(Artifact):
    name: str
    parameters: dict = field(default_factory=dict)
