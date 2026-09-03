from runa.agent import Agent
from runa.core import EventType, Message, Role, Run, ToolCall
from runa.observability import instrument, timeline
from runa.runtime import Executor
from runa.tool import Tool
from tests.fakes import FakeProvider


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
