import pytest

from runa.core import Context, ConversationState, Run, RunState


def test_run_context_supports_attribute_access():
    context = Context()
    context.resources = ["kb-1"]
    assert context.resources == ["kb-1"]
    assert context["resources"] == ["kb-1"]


def test_new_run_starts_with_an_empty_context():
    run = Run(input="hello")
    assert isinstance(run.context, Context)
    assert dict(run.context) == {}


def test_run_state_supports_attribute_access():
    state = RunState()
    state.plan = ["step 1"]
    assert state.plan == ["step 1"]
    assert state["plan"] == ["step 1"]


def test_conversation_state_supports_attribute_access():
    state = ConversationState()
    state.preferences = {"lang": "en"}
    assert state.preferences == {"lang": "en"}


def test_missing_attribute_raises():
    state = RunState()
    with pytest.raises(AttributeError):
        _ = state.missing
