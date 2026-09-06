import threading
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
    assert loaded is not None

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

    reloaded = store.get(run.id)
    assert reloaded is not None
    assert reloaded.result == "done"
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
    assert loaded is not None

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
    assert loaded is not None

    assert loaded.messages[0].role == Role.ASSISTANT
    assert loaded.messages[0].tool_calls[0].name == "send_refund"
    assert loaded.messages[0].tool_calls[0].idempotent is True
    assert loaded.messages[0].tool_calls[0].effect == EffectStatus.OBSERVED
    assert isinstance(loaded.artifacts[0], TextArtifact)
    assert loaded.artifacts[0].text == "refunded"
    assert any(e.type == EventType.MODEL_CALLED for e in loaded.events)
    assert isinstance(loaded.events[0], Event)


def test_round_trips_a_messages_usage():
    store = SQLiteRunStore(":memory:")
    run = Run(input="hi")
    run.add_message(
        Message(
            role=Role.ASSISTANT,
            content="hi there",
            usage={"input_tokens": 10, "output_tokens": 3},
        )
    )

    store.save(run)
    loaded = store.get(run.id)
    assert loaded is not None

    assert loaded.messages[0].usage == {"input_tokens": 10, "output_tokens": 3}


def test_round_trips_a_failed_runs_error():
    store = SQLiteRunStore(":memory:")
    run = Run(input="hi")
    run.start()
    run.fail("boom")

    store.save(run)
    loaded = store.get(run.id)
    assert loaded is not None

    assert loaded.error == "boom"


def test_round_trips_a_tool_calls_non_json_safe_result_as_a_string():
    # A Tool may return an Artifact (or any object); ToolCall.result holds
    # it as-is, but persistence can't; it should fall back to str() rather
    # than raise and lose the whole Run.
    store = SQLiteRunStore(":memory:")
    run = Run(input="hi")
    artifact = TextArtifact(text="a report")
    tool_call = ToolCall(name="MakeReport", result=artifact, attempts=1)
    run.add_message(Message(role=Role.ASSISTANT, tool_calls=[tool_call]))

    store.save(run)
    loaded = store.get(run.id)
    assert loaded is not None

    assert loaded.tool_calls[0].result == str(artifact)


def test_round_trips_state_with_a_non_json_safe_value():
    # Same concern as ToolCall.result, but for the other place the docs
    # invite an arbitrary object into: run.state.
    store = SQLiteRunStore(":memory:")
    run = Run(input="hi")
    artifact = TextArtifact(text="a finding")
    run.state.findings = [artifact]
    run.state.sources = ["a plain string"]

    store.save(run)
    loaded = store.get(run.id)
    assert loaded is not None

    assert loaded.state.findings == str([artifact])
    assert loaded.state.sources == ["a plain string"]


def test_round_trips_a_non_json_safe_input_and_result_as_strings():
    # Same concern again, for Run.input and Run.result: Agent.run(input:
    # Any, ...) places no constraint on input, and architecture.md §2
    # expects Result to hold structured objects, not just text; save()
    # must not crash and lose the whole Run over either one.
    store = SQLiteRunStore(":memory:")
    input_artifact = TextArtifact(text="the input")
    result_artifact = TextArtifact(text="the result")
    run = Run(input=input_artifact)
    run.start()
    run.complete(result=result_artifact)

    store.save(run)
    loaded = store.get(run.id)
    assert loaded is not None

    assert loaded.input == str(input_artifact)
    assert loaded.result == str(result_artifact)


def test_round_trips_agent_nameentity_and_version():
    store = SQLiteRunStore(":memory:")
    run = Run(input="hi", agent_name="ResearchAgent", agent_version="1.2.0")

    store.save(run)
    loaded = store.get(run.id)
    assert loaded is not None

    assert loaded.agent_name == "ResearchAgent"
    assert loaded.agent_version == "1.2.0"


def test_list_filters_by_agent_name():
    store = SQLiteRunStore(":memory:")
    research = Run(input="one", agent_name="ResearchAgent")
    support = Run(input="two", agent_name="SupportAgent")
    store.save(research)
    store.save(support)

    matches = store.list(agent_name="ResearchAgent")

    assert [run.id for run in matches] == [research.id]


def test_round_trips_parent_run_id():
    store = SQLiteRunStore(":memory:")
    parent = Run(input="parent")
    child = Run(input="child", parent_run_id=parent.id)

    store.save(parent)
    store.save(child)
    loaded = store.get(child.id)
    assert loaded is not None

    assert loaded.parent_run_id == parent.id


def test_list_filters_by_parent_run_id():
    store = SQLiteRunStore(":memory:")
    parent = Run(input="parent")
    child = Run(input="child", parent_run_id=parent.id)
    other = Run(input="unrelated")
    store.save(parent)
    store.save(child)
    store.save(other)

    matches = store.list(parent_run_id=parent.id)

    assert [run.id for run in matches] == [child.id]


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


def test_concurrent_save_and_get_from_multiple_threads_does_not_corrupt_data():
    # check_same_thread=False only lifts sqlite3's same-thread check; a
    # shared Connection still isn't safe to call from multiple threads at
    # once without external locking. Drive real overlap with a barrier so
    # every thread's execute()/commit() genuinely interleaves.
    store = SQLiteRunStore(":memory:")
    runs = [Run(input=f"input-{i}") for i in range(20)]
    for run in runs:
        store.save(run)

    errors: list[Exception] = []
    barrier = threading.Barrier(8)

    def hammer(worker_id: int) -> None:
        barrier.wait()
        for i in range(50):
            run = runs[(worker_id * 50 + i) % len(runs)]
            try:
                store.save(run)
                loaded = store.get(run.id)
                if loaded is None:
                    raise AssertionError(f"get returned None for {run.id}")
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

    threads = [threading.Thread(target=hammer, args=(i,)) for i in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []


def test_a_tool_call_found_via_run_tool_calls_is_the_same_object_in_its_message():
    store = SQLiteRunStore(":memory:")
    run = Run(input="refund order A123")
    tool_call = ToolCall(name="send_refund", arguments={"order_id": "A123"})
    run.add_message(Message(role=Role.ASSISTANT, content="", tool_calls=[tool_call]))

    store.save(run)
    loaded = store.get(run.id)
    assert loaded is not None

    pending = loaded.tool_calls[0]
    pending.approved = True

    assert loaded.messages[0].tool_calls[0].approved is True
