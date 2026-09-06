from runa.core import (
    Artifact,
    DataArtifact,
    FileArtifact,
    TextArtifact,
)


def test_text_artifact_requires_text():
    artifact = TextArtifact(text="hello")
    assert artifact.text == "hello"
    assert artifact.id


def test_data_artifact_holds_structured_data():
    artifact = DataArtifact(data={"score": 0.9})
    assert artifact.data["score"] == 0.9


def test_data_artifact_is_not_restricted_to_dict():
    assert DataArtifact(data=[1, 2, 3]).data == [1, 2, 3]
    assert DataArtifact(data="plain text").data == "plain text"
    assert DataArtifact().data is None


def test_base_artifact_summary_mentions_its_id():
    artifact = Artifact()
    assert artifact.id in artifact.summary()


def test_text_artifact_summary_is_the_text():
    assert TextArtifact(text="hello").summary() == "hello"


def test_data_artifact_summary_is_the_data():
    assert DataArtifact(data={"score": 0.9}).summary() == "{'score': 0.9}"


def test_file_artifact_summary_mentions_the_uri():
    assert (
        FileArtifact(uri="s3://bucket/report.pdf").summary()
        == "file created: s3://bucket/report.pdf"
    )
