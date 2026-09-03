from runa.core import (
    ActionArtifact,
    Artifact,
    CitationSetArtifact,
    DataArtifact,
    FileArtifact,
    PlanArtifact,
    TextArtifact,
)


def test_text_artifact_requires_text():
    artifact = TextArtifact(text="hello")
    assert artifact.text == "hello"
    assert artifact.id


def test_data_artifact_holds_structured_data():
    artifact = DataArtifact(data={"score": 0.9})
    assert artifact.data["score"] == 0.9


def test_action_artifact_holds_name_and_parameters():
    artifact = ActionArtifact(name="transfer_funds", parameters={"amount": 10})
    assert artifact.name == "transfer_funds"


def test_base_artifact_summary_mentions_its_id():
    artifact = Artifact()
    assert artifact.id in artifact.summary()


def test_text_artifact_summary_is_the_text():
    assert TextArtifact(text="hello").summary() == "hello"


def test_data_artifact_summary_is_the_data():
    assert DataArtifact(data={"score": 0.9}).summary() == "{'score': 0.9}"


def test_file_artifact_summary_mentions_the_path():
    assert (
        FileArtifact(path="/tmp/report.pdf").summary()
        == "file created: /tmp/report.pdf"
    )


def test_citation_set_artifact_summary_lists_citations():
    artifact = CitationSetArtifact(citations=["a.com", "b.com"])
    assert artifact.summary() == "a.com\nb.com"


def test_plan_artifact_summary_numbers_the_steps():
    artifact = PlanArtifact(steps=["search", "summarize"])
    assert artifact.summary() == "1. search\n2. summarize"


def test_action_artifact_summary_looks_like_a_call():
    artifact = ActionArtifact(name="transfer_funds", parameters={"amount": 10})
    assert artifact.summary() == "transfer_funds({'amount': 10})"
