from datetime import UTC, datetime, timedelta

from runa.core import (
    EffectStatus,
    Event,
    EventType,
    Message,
    Role,
    Run,
    RunStatus,
    TextArtifact,
    ToolCall,
)
from runa.persistence import SQLiteRunStore


def test_save_and_get_round_trips_a_run():
    store = SQLiteRunStore(":memory:")
    run = Run(input="hi")

    store.save(run)
    loaded = store.get(run.id)

    assert loaded is not run
    assert loaded.id == run.id
    assert loaded.input == "hi"
    assert loaded.status == RunStatus.CREATED


def test_get_missing_run_returns_none():
    store = SQLiteRunStore(":memory:")

    assert store.get("does-not-exist") is None


def test_list_returns_all_saved_runs():
    store = SQLiteRunStore(":memory:")
    first = Run(input="one")
    second = Run(input="two")

    store.save(first)
    store.save(second)

    assert {run.id for run in store.list()} == {first.id, second.id}


def test_save_again_overwrites_the_previous_version():
    store = SQLiteRunStore(":memory:")
    run = Run(input="hi")
    store.save(run)

    run.start()
    run.complete(result="done")
    store.save(run)

    assert store.get(run.id).result == "done"
    assert len(store.list()) == 1


def test_survives_reopening_the_same_database_file(tmp_path):
    path = str(tmp_path / "runs.sqlite3")
    run = Run(input="hi")
    run.start()

    first_connection = SQLiteRunStore(path)
    first_connection.save(run)
    first_connection.close()

    second_connection = SQLiteRunStore(path)
    loaded = second_connection.get(run.id)

    assert loaded.id == run.id
    assert loaded.status == RunStatus.RUNNING


def test_round_trips_messages_tool_calls_artifacts_and_events():
    store = SQLiteRunStore(":memory:")
    run = Run(input="refund order A123")
    tool_call = ToolCall(
        name="send_refund",
        arguments={"order_id": "A123"},
        idempotent=True,
        effect=EffectStatus.OBSERVED,
    )
    run.add_message(Message(role=Role.ASSISTANT, content="", tool_calls=[tool_call]))
    run.add_artifact(TextArtifact(text="refunded"))
    run.emit(EventType.MODEL_CALLED, model="gpt-5-nano")

    store.save(run)
    loaded = store.get(run.id)

    assert loaded.messages[0].role == Role.ASSISTANT
    assert loaded.messages[0].tool_calls[0].name == "send_refund"
    assert loaded.messages[0].tool_calls[0].idempotent is True
    assert loaded.messages[0].tool_calls[0].effect == EffectStatus.OBSERVED
    assert isinstance(loaded.artifacts[0], TextArtifact)
    assert loaded.artifacts[0].text == "refunded"
    assert any(e.type == EventType.MODEL_CALLED for e in loaded.events)
    assert isinstance(loaded.events[0], Event)


def test_list_filters_by_status():
    store = SQLiteRunStore(":memory:")
    completed = Run(input="one")
    completed.start()
    completed.complete(result="done")
    failed = Run(input="two")
    failed.start()
    failed.fail("boom")
    store.save(completed)
    store.save(failed)

    assert [r.id for r in store.list(status=RunStatus.COMPLETED)] == [completed.id]
    assert [r.id for r in store.list(status=RunStatus.FAILED)] == [failed.id]


def test_list_filters_by_since():
    store = SQLiteRunStore(":memory:")
    old = Run(input="old", created_at=datetime.now(UTC) - timedelta(days=1))
    recent = Run(input="recent")
    store.save(old)
    store.save(recent)

    matches = store.list(since=datetime.now(UTC) - timedelta(hours=1))

    assert [r.id for r in matches] == [recent.id]


def test_a_tool_call_found_via_run_tool_calls_is_the_same_object_in_its_message():
    store = SQLiteRunStore(":memory:")
    run = Run(input="refund order A123")
    tool_call = ToolCall(name="send_refund", arguments={"order_id": "A123"})
    run.add_message(Message(role=Role.ASSISTANT, content="", tool_calls=[tool_call]))

    store.save(run)
    loaded = store.get(run.id)

    pending = loaded.tool_calls[0]
    pending.approved = True

    assert loaded.messages[0].tool_calls[0].approved is True
