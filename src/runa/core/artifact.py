"""Artifact: first-class, non-text-only output produced during a Run.

A Tool's `call()` may return an Artifact instead of a plain value: the
Executor recognizes it by type (manifesto §2: "types are configuration")
and records it on the Run automatically (see `runtime/executor.py`), so
"agents create artifacts" (manifesto §10) is a normal consequence of a tool
running, not a separate API a developer has to remember to call.
`summary()` is what the model sees as that tool call's result; override it
on a custom Artifact subclass to control that text.

RUNA core owns the Artifact lifecycle (recognition, recording on a Run,
`summary()` as the model-facing representation) and a small set of
genuinely universal shapes: `TextArtifact`, `DataArtifact`, `FileArtifact`.
It does not own an expanding taxonomy of domain-specific outputs. What an
Artifact actually represents (a research report's citations, a deployment
plan's steps) belongs to the application, not the runtime: subclass
`Artifact` directly, e.g.

    @dataclass(kw_only=True)
    class ResearchArtifact(Artifact):
        citations: list[str]

    @dataclass(kw_only=True)
    class DeploymentPlan(Artifact):
        steps: list[str]

The Run and Executor only ever depend on the base `Artifact` contract
(`id`, `created_at`, `summary()`); they don't need to know an application's
subclasses exist. An Artifact is something a Run *produced*, not something
that *happened*; an executed operation is a `ToolCall` (`core/message.py`,
see `docs/concepts.md`'s Action section), not an Artifact.

`artifact_type()` is a second, separate contract: the *durable* identity
persistence writes down for an Artifact, as opposed to `type(artifact)`,
its *current Python implementation*. The two coincide by default (a dotted
`module.ClassName` path, cheap and zero-config), but a dotted path is a
Python location, not a stable identity: modules move, classes get renamed,
a persisted Run may need to survive that. An application that cares about
surviving such a move overrides `artifact_type()` with a string it
controls and owns independently of where the class currently lives, e.g.:

    class ResearchArtifact(Artifact):
        @classmethod
        def artifact_type(cls) -> str:
            return "myapp.research_artifact"

See `persistence/serialize.py` for how this tag is resolved back to a
class on load.
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class Artifact:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def summary(self) -> str:
        """Plain-text form fed back to the model as the tool call's result."""
        return f"artifact created: {self.id}"

    @classmethod
    def artifact_type(cls) -> str:
        """The durable type tag persistence stores for this Artifact.

        Defaults to a dotted `module.ClassName` path: zero-config, but a
        Python location, not a claim that this path is durable. Override
        it to give this Artifact a stable identity that survives the class
        being moved or renamed (see the module docstring).
        """
        return f"{cls.__module__}.{cls.__qualname__}"


@dataclass(kw_only=True)
class TextArtifact(Artifact):
    text: str

    def summary(self) -> str:
        return self.text


@dataclass(kw_only=True)
class DataArtifact(Artifact):
    """Structured, JSON-like output: not restricted to `dict`.

    A tool may naturally produce a list, a scalar, or a nested mix of
    those; constraining `data` to `dict` would just push applications to
    wrap it in one (`{"items": [...]}`) for no runtime benefit.
    """

    data: Any = None

    def summary(self) -> str:
        return str(self.data)


@dataclass(kw_only=True)
class FileArtifact(Artifact):
    """A file the Tool produced, addressed by `uri` rather than local `path`.

    A local path is one case of `uri` (`file:///tmp/report.pdf`, or a bare
    path if the application only ever deals in local files); it also
    supports object storage (`s3://...`) and other external locations
    without RUNA core needing to know which.
    """

    uri: str
    mime_type: str | None = None

    def summary(self) -> str:
        return f"file created: {self.uri}"
