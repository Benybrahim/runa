from runa.core import ActionArtifact, DataArtifact, TextArtifact


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
