from dataclasses import dataclass

import pytest

from runa.core import Artifact, DataArtifact, FileArtifact, Run, TextArtifact
from runa.persistence.serialize import run_from_dict, run_to_dict


@dataclass(kw_only=True)
class ResearchArtifact(Artifact):
    """An application-defined Artifact subclass, not part of RUNA core."""

    citations: list[str]

    def summary(self) -> str:
        return "\n".join(self.citations)

    @classmethod
    def artifact_type(cls) -> str:
        return "research:v1"


@dataclass(kw_only=True)
class ResearchArtifactRenamed(Artifact):
    """Stands in for `ResearchArtifact` after a hypothetical move/rename:
    a distinct class, at a distinct import path, that an application would
    map the old `"research:v1"` tag onto going forward."""

    citations: list[str]


def test_builtin_artifacts_round_trip_by_default_dotted_path_tag():
    run = Run(input="report")
    run.add_artifact(TextArtifact(text="hello"))
    run.add_artifact(DataArtifact(data=[1, 2, 3]))
    run.add_artifact(FileArtifact(uri="s3://bucket/report.pdf"))

    data = run_to_dict(run)
    assert data["artifacts"][0]["type"] == "runa.core.artifact.TextArtifact"

    loaded = run_from_dict(data)

    assert isinstance(loaded.artifacts[0], TextArtifact)
    assert loaded.artifacts[0].text == "hello"
    assert isinstance(loaded.artifacts[1], DataArtifact)
    assert loaded.artifacts[1].data == [1, 2, 3]
    assert isinstance(loaded.artifacts[2], FileArtifact)
    assert loaded.artifacts[2].uri == "s3://bucket/report.pdf"


def test_application_defined_subclass_persists_its_own_stable_tag():
    """RUNA core doesn't know ResearchArtifact exists; the tag it persists
    is whatever the subclass's own `artifact_type()` returns, not an
    implicit dotted path to wherever the class happens to live."""
    run = Run(input="research task")
    run.add_artifact(ResearchArtifact(citations=["a.com", "b.com"]))

    data = run_to_dict(run)

    assert data["artifacts"][0]["type"] == "research:v1"


def test_explicit_mapping_resolves_a_stable_tag_the_import_fallback_cannot():
    """`"research:v1"` isn't a `module.ClassName` path, so the default
    import fallback can't resolve it on its own; an application-supplied
    mapping is required, and is consulted first."""
    run = Run(input="research task")
    run.add_artifact(ResearchArtifact(citations=["a.com", "b.com"]))
    data = run_to_dict(run)

    with pytest.raises(LookupError):
        run_from_dict(data)

    loaded = run_from_dict(data, artifact_resolver={"research:v1": ResearchArtifact})

    assert isinstance(loaded.artifacts[0], ResearchArtifact)
    assert loaded.artifacts[0].citations == ["a.com", "b.com"]


def test_stable_tag_survives_a_python_implementation_path_that_moved():
    """The stored tag is the durable identity; which class it resolves to
    is entirely up to the mapping passed at load time, not anything
    recoverable from the tag itself. This is what lets an application move
    or rename the class `"research:v1"` originally pointed at and still
    load Runs persisted before the move."""
    run = Run(input="research task")
    run.add_artifact(ResearchArtifact(citations=["a.com", "b.com"]))
    data = run_to_dict(run)

    loaded = run_from_dict(
        data, artifact_resolver={"research:v1": ResearchArtifactRenamed}
    )

    assert isinstance(loaded.artifacts[0], ResearchArtifactRenamed)
    assert not isinstance(loaded.artifacts[0], ResearchArtifact)
    assert loaded.artifacts[0].citations == ["a.com", "b.com"]
