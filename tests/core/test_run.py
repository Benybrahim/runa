import pytest

from runa.core import (
    EventType,
    IllegalTransition,
    Message,
    Role,
    Run,
    RunStatus,
    TextArtifact,
)


def test_new_run_starts_created():
    run = Run(input="hello")
    assert run.status == RunStatus.CREATED
    assert run.events == []


def test_new_run_has_no_agent_provenance_until_stamped():
    run = Run(input="hello")
    assert run.agent_name is None
    assert run.agent_version is None


def test_start_transitions_to_running_and_emits_event():
    run = Run(input="hello")
    run.start()
    assert run.status == RunStatus.RUNNING
    assert run.events[-1].type == EventType.RUN_STARTED


def test_complete_sets_result_and_status():
    run = Run(input="hello")
    run.start()
    run.complete(result="done")
    assert run.status == RunStatus.COMPLETED
    assert run.result == "done"
    assert run.is_terminal


def test_pause_and_resume_round_trip():
    run = Run(input="hello")
    run.start()
    run.pause()
    assert run.status == RunStatus.PAUSED
    run.resume()
    assert run.status == RunStatus.RUNNING
    assert run.events[-1].type == EventType.RUN_RESUMED


def test_require_approval_carries_tool_call_id():
    run = Run(input="hello")
    run.start()
    run.require_approval(tool_call_id="tc-1")
    assert run.status == RunStatus.AWAITING_APPROVAL
    assert run.events[-1].data["tool_call_id"] == "tc-1"


def test_illegal_transition_raises():
    run = Run(input="hello")
    with pytest.raises(IllegalTransition):
        run.complete()  # cannot complete a run that never started


def test_terminal_run_cannot_transition_again():
    run = Run(input="hello")
    run.start()
    run.fail(error="boom")
    assert run.is_terminal
    with pytest.raises(IllegalTransition):
        run.start()


def test_add_message_and_artifact():
    run = Run(input="hello")
    run.add_message(Message(role=Role.USER, content="hi"))
    assert len(run.messages) == 1

    run.add_artifact(TextArtifact(text="a report"))
    assert len(run.artifacts) == 1
    assert run.events[-1].type == EventType.ARTIFACT_CREATED
