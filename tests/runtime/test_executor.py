from runa.agent import Agent
from runa.core import EventType, Message, Role, Run, RunStatus, ToolCall
from runa.runtime.executor import Executor
from runa.runtime.strategy import CallModel, Complete, Strategy
from runa.tool import Tool
from tests.fakes import FakeProvider


class GetWeather(Tool):
    def call(self, city: str) -> str:
        return f"{city}: sunny"


class WeatherAgent(Agent):
    instructions = "Answer weather questions."
    tools = [GetWeather]


def test_executor_runs_a_full_tool_use_loop():
    provider = FakeProvider(
        responses=[
            Message(
                role=Role.ASSISTANT,
                tool_calls=[ToolCall(name="GetWeather", arguments={"city": "Tokyo"})],
            ),
            Message(role=Role.ASSISTANT, content="Tokyo is sunny."),
        ]
    )
    executor = Executor(provider)
    agent = WeatherAgent()
    run = Run(input="What's the weather in Tokyo?")

    result = executor.run(agent, run)

    assert result.status == RunStatus.COMPLETED
    assert result.result == "Tokyo is sunny."
    assert len(provider.calls) == 2

    # system + user seed, assistant tool-call, tool result, final assistant
    roles = [message.role for message in result.messages]
    assert roles == [
        Role.SYSTEM,
        Role.USER,
        Role.ASSISTANT,
        Role.TOOL,
        Role.ASSISTANT,
    ]

    event_types = [event.type for event in result.events]
    assert event_types == [
        EventType.RUN_STARTED,
        EventType.MODEL_CALLED,
        EventType.MODEL_RESPONDED,
        EventType.TOOL_CALLED,
        EventType.TOOL_COMPLETED,
        EventType.MODEL_CALLED,
        EventType.MODEL_RESPONDED,
        EventType.RUN_COMPLETED,
    ]


def test_executor_answers_directly_without_tools():
    provider = FakeProvider(
        responses=[Message(role=Role.ASSISTANT, content="No tools needed.")]
    )
    executor = Executor(provider)
    agent = WeatherAgent()
    run = Run(input="hello")

    result = executor.run(agent, run)

    assert result.status == RunStatus.COMPLETED
    assert result.result == "No tools needed."
    assert len(provider.calls) == 1


def test_tool_exception_fails_the_run():
    class BrokenTool(Tool):
        def call(self) -> None:
            raise RuntimeError("boom")

    class BrokenAgent(Agent):
        tools = [BrokenTool]

    provider = FakeProvider(
        responses=[
            Message(
                role=Role.ASSISTANT,
                tool_calls=[ToolCall(name="BrokenTool", arguments={})],
            )
        ]
    )
    executor = Executor(provider)
    run = Run(input="do the thing")

    result = executor.run(BrokenAgent(), run)

    assert result.status == RunStatus.FAILED
    assert "boom" in result.events[-1].data["error"]


def test_max_steps_fails_the_run_instead_of_looping_forever():
    class NeverEndingStrategy:
        def step(self, run):
            return CallModel()

    provider = FakeProvider(
        responses=[Message(role=Role.ASSISTANT, content="ignored")] * 100
    )
    executor = Executor(provider, strategy=NeverEndingStrategy(), max_steps=3)
    run = Run(input="loop forever")

    result = executor.run(WeatherAgent(), run)

    assert result.status == RunStatus.FAILED
    assert "max_steps" in result.events[-1].data["error"]


def test_agent_hooks_are_called_around_execution():
    calls = []

    class HookedAgent(Agent):
        def before_run(self, run):
            calls.append("before_run")

        def after_run(self, run):
            calls.append("after_run")

    provider = FakeProvider(responses=[Message(role=Role.ASSISTANT, content="ok")])
    Executor(provider).run(HookedAgent(), Run(input="hi"))

    assert calls == ["before_run", "after_run"]


def test_strategy_protocol_is_satisfiable_without_inheritance():
    class AlwaysComplete:
        def step(self, run):
            return Complete(result="done")

    strategy: Strategy = AlwaysComplete()
    provider = FakeProvider(responses=[])
    result = Executor(provider, strategy=strategy).run(WeatherAgent(), Run(input="x"))

    assert result.status == RunStatus.COMPLETED
    assert result.result == "done"
