import asyncio

import pytest

from runa.agent import Agent
from runa.background import run_later
from runa.core import EventType, Message, Role, Run, RunStatus, ToolCall
from runa.observability import instrument, timeline
from runa.runtime import AsyncExecutor, Executor
from runa.tool import Tool
from tests.fakes import FakeAsyncProvider, FakeProvider


class GreeterAgent(Agent):
    instructions = "Say hello."


class GetWeather(Tool):
    def call(self, city: str) -> str:
        return f"{city}: sunny"


class WeatherAgent(Agent):
    tools = [GetWeather]


class BrokenTool(Tool):
    def call(self, city: str) -> str:
        raise RuntimeError("boom")


class BrokenAgent(Agent):
    tools = [BrokenTool]


class NamedModelAgent(Agent):
    model = "claude-sonnet-5"


def test_timeline_summarizes_a_direct_answer_with_the_model_and_content():
    provider = FakeProvider(responses=[Message(role=Role.ASSISTANT, content="hi")])
    run = Executor(provider).run(NamedModelAgent(), Run(input="hello"))

    called = next(e for e in timeline(run) if e.type == EventType.MODEL_CALLED)
    responded = next(e for e in timeline(run) if e.type == EventType.MODEL_RESPONDED)

    assert called.summary == "model called (claude-sonnet-5)"
    assert responded.summary == "model responded: 'hi'"


def test_timeline_summarizes_a_response_with_usage_when_the_provider_reports_it():
    provider = FakeProvider(
        responses=[
            Message(
                role=Role.ASSISTANT,
                content="hi",
                usage={"input_tokens": 10, "output_tokens": 3},
            )
        ]
    )
    run = Executor(provider).run(NamedModelAgent(), Run(input="hello"))

    responded = next(e for e in timeline(run) if e.type == EventType.MODEL_RESPONDED)

    assert responded.summary == "model responded: 'hi' (10 in / 3 out)"


def test_timeline_summarizes_a_model_call_with_no_configured_model():
    provider = FakeProvider(responses=[Message(role=Role.ASSISTANT, content="hi")])
    run = Executor(provider).run(GreeterAgent(), Run(input="hello"))

    called = next(e for e in timeline(run) if e.type == EventType.MODEL_CALLED)

    assert called.summary == "model called"


def test_timeline_summarizes_a_tool_requesting_response_by_call_count():
    provider = FakeProvider(
        responses=[
            Message(
                role=Role.ASSISTANT,
                tool_calls=[
                    ToolCall(name="GetWeather", arguments={"city": "Tokyo"}),
                    ToolCall(name="GetWeather", arguments={"city": "Osaka"}),
                ],
            ),
            Message(role=Role.ASSISTANT, content="Both sunny."),
        ]
    )
    run = Executor(provider).run(WeatherAgent(), Run(input="weather?"))

    responded = next(e for e in timeline(run) if e.type == EventType.MODEL_RESPONDED)

    assert responded.summary == "model responded: requested 2 tool call(s)"


def test_timeline_summarizes_events_in_order():
    provider = FakeProvider(responses=[Message(role=Role.ASSISTANT, content="hi")])
    run = Executor(provider).run(GreeterAgent(), Run(input="hello"))

    entries = timeline(run)

    assert [entry.type for entry in entries] == [
        EventType.RUN_STARTED,
        EventType.MODEL_CALLED,
        EventType.MODEL_RESPONDED,
        EventType.RUN_COMPLETED,
    ]
    assert entries[0].summary == "run started"
    assert entries[-1].summary == "run completed"
    assert all(entry.timestamp is not None for entry in entries)


def test_timeline_summarizes_a_tool_call_with_its_arguments():
    provider = FakeProvider(
        responses=[
            Message(
                role=Role.ASSISTANT,
                tool_calls=[ToolCall(name="GetWeather", arguments={"city": "Tokyo"})],
            ),
            Message(role=Role.ASSISTANT, content="sunny"),
        ]
    )
    run = Executor(provider).run(WeatherAgent(), Run(input="weather in Tokyo?"))

    called = next(e for e in timeline(run) if e.type == EventType.TOOL_CALLED)
    completed = next(e for e in timeline(run) if e.type == EventType.TOOL_COMPLETED)

    assert called.summary == "tool called: GetWeather({'city': 'Tokyo'})"
    assert completed.summary == "tool completed: GetWeather -> 'Tokyo: sunny'"


def test_timeline_summarizes_a_failed_tool_call_with_its_arguments():
    provider = FakeProvider(
        responses=[
            Message(
                role=Role.ASSISTANT,
                tool_calls=[ToolCall(name="BrokenTool", arguments={"city": "Tokyo"})],
            ),
        ]
    )
    run = Executor(provider).run(BrokenAgent(), Run(input="weather in Tokyo?"))

    failed = next(e for e in timeline(run) if e.type == EventType.TOOL_FAILED)

    assert failed.summary == "tool failed: BrokenTool({'city': 'Tokyo'}): boom"


def test_timeline_reflects_run_events_not_a_separate_copy():
    provider = FakeProvider(responses=[Message(role=Role.ASSISTANT, content="hi")])
    run = Run(input="hello")

    assert timeline(run) == []

    Executor(provider).run(GreeterAgent(), run)

    assert len(timeline(run)) == len(run.events)


def test_instrument_notifies_subscriber_as_events_happen():
    seen = []
    provider = FakeProvider(responses=[Message(role=Role.ASSISTANT, content="hi")])
    run = Run(input="hello")

    instrument(run, seen.append)
    Executor(provider).run(GreeterAgent(), run)

    assert [event.type for event in seen] == [
        EventType.RUN_STARTED,
        EventType.MODEL_CALLED,
        EventType.MODEL_RESPONDED,
        EventType.RUN_COMPLETED,
    ]
    assert seen == run.events


def test_instrument_supports_multiple_subscribers():
    first, second = [], []
    run = Run(input="hello")

    instrument(run, first.append)
    instrument(run, second.append)
    run.start()

    assert [event.type for event in first] == [EventType.RUN_STARTED]
    assert [event.type for event in second] == [EventType.RUN_STARTED]


def test_a_raising_subscriber_does_not_fail_or_crash_the_run():
    # Before this, an exception from a subscriber (e.g. a webhook endpoint
    # that's down) propagated straight out of Executor.run() — including
    # from run.start(), which fires outside the Executor's own try/except —
    # defeating the guarantee that Run execution converts failures into a
    # failed Run rather than crashing the caller.
    provider = FakeProvider(responses=[Message(role=Role.ASSISTANT, content="hi")])
    run = Run(input="hello")

    def broken_subscriber(event):
        raise ConnectionError("endpoint unreachable")

    instrument(run, broken_subscriber)

    with pytest.warns(RuntimeWarning, match="endpoint unreachable"):
        result = Executor(provider).run(GreeterAgent(), run)

    assert result.status == RunStatus.COMPLETED
    assert result.result == "hi"


def test_a_raising_subscriber_does_not_block_other_subscribers():
    seen = []
    run = Run(input="hello")

    def broken_subscriber(event):
        raise RuntimeError("boom")

    instrument(run, broken_subscriber)
    instrument(run, seen.append)

    with pytest.warns(RuntimeWarning):
        run.start()

    assert [event.type for event in seen] == [EventType.RUN_STARTED]


def test_timeline_works_for_a_run_async_run_with_no_runstore():
    provider = FakeAsyncProvider(responses=[Message(role=Role.ASSISTANT, content="hi")])
    run = asyncio.run(AsyncExecutor(provider).run(GreeterAgent(), Run(input="hello")))

    assert [entry.type for entry in timeline(run)] == [
        EventType.RUN_STARTED,
        EventType.MODEL_CALLED,
        EventType.MODEL_RESPONDED,
        EventType.RUN_COMPLETED,
    ]


def test_timeline_works_for_a_run_later_run_with_no_runstore():
    provider = FakeProvider(responses=[Message(role=Role.ASSISTANT, content="hi")])
    run = run_later(GreeterAgent(), Run(input="hello"), Executor(provider))

    assert [entry.type for entry in timeline(run)] == [
        EventType.RUN_QUEUED,
        EventType.RUN_STARTED,
        EventType.MODEL_CALLED,
        EventType.MODEL_RESPONDED,
        EventType.RUN_COMPLETED,
    ]


def test_separate_runs_have_isolated_event_histories():
    provider = FakeProvider(
        responses=[
            Message(role=Role.ASSISTANT, content="hi"),
            Message(role=Role.ASSISTANT, content="bye"),
        ]
    )
    executor = Executor(provider)
    first = executor.run(GreeterAgent(), Run(input="hello"))
    second = executor.run(GreeterAgent(), Run(input="goodbye"))

    assert first.id != second.id
    assert first.events is not second.events
    assert [e.type for e in timeline(first)] == [e.type for e in timeline(second)]
    # mutating one Run's event log must not leak into the other's
    first.emit(EventType.ARTIFACT_CREATED, artifact_id="x")
    assert len(timeline(first)) != len(timeline(second))


def test_unsubscribe_stops_further_notifications():
    seen = []
    run = Run(input="hello")

    unsubscribe = instrument(run, seen.append)
    run.start()
    unsubscribe()
    run.pause()

    assert [event.type for event in seen] == [EventType.RUN_STARTED]
    assert [event.type for event in run.events] == [
        EventType.RUN_STARTED,
        EventType.RUN_PAUSED,
    ]
