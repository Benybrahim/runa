from runa.agent import Agent
from runa.approval import approve
from runa.core import DataArtifact, EventType, Message, Role, Run, RunStatus, ToolCall
from runa.runtime.executor import Executor
from runa.runtime.retry import RetryStrategy
from runa.runtime.strategy import CallModel, Complete, Fail, Strategy
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

    tool_failed = next(e for e in result.events if e.type == EventType.TOOL_FAILED)
    assert tool_failed.data["error"] == "boom"
    assert result.tool_calls[0].error == "boom"
    assert result.tool_calls[0].attempts == 1


def test_retry_strategy_retries_a_flaky_tool_before_succeeding():
    class FlakyTool(Tool):
        calls = 0

        def call(self) -> str:
            FlakyTool.calls += 1
            if FlakyTool.calls < 3:
                raise RuntimeError("still flaky")
            return "ok"

    class FlakyAgent(Agent):
        tools = [FlakyTool]

    provider = FakeProvider(
        responses=[
            Message(
                role=Role.ASSISTANT,
                tool_calls=[ToolCall(name="FlakyTool", arguments={})],
            ),
            Message(role=Role.ASSISTANT, content="done"),
        ]
    )
    executor = Executor(provider, strategy=RetryStrategy(max_retries=3))
    run = Run(input="do the flaky thing")

    result = executor.run(FlakyAgent(), run)

    assert result.status == RunStatus.COMPLETED
    assert result.result == "done"
    assert FlakyTool.calls == 3
    assert result.tool_calls[0].attempts == 3
    assert result.tool_calls[0].error is None


def test_retry_strategy_fails_after_exhausting_retries():
    class AlwaysBroken(Tool):
        def call(self) -> None:
            raise RuntimeError("nope")

    class BrokenAgent(Agent):
        tools = [AlwaysBroken]

    provider = FakeProvider(
        responses=[
            Message(
                role=Role.ASSISTANT,
                tool_calls=[ToolCall(name="AlwaysBroken", arguments={})],
            )
        ]
    )
    executor = Executor(provider, strategy=RetryStrategy(max_retries=2))
    run = Run(input="do the thing")

    result = executor.run(BrokenAgent(), run)

    assert result.status == RunStatus.FAILED
    assert "nope" in result.events[-1].data["error"]
    assert result.tool_calls[0].attempts == 3


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

        def plan(self, run):
            calls.append("plan")

        def review(self, run):
            calls.append("review")

        def after_run(self, run):
            calls.append("after_run")

    provider = FakeProvider(responses=[Message(role=Role.ASSISTANT, content="ok")])
    Executor(provider).run(HookedAgent(), Run(input="hi"))

    assert calls == ["before_run", "plan", "review", "after_run"]


def test_review_hook_is_skipped_when_the_run_fails_instead_of_completing():
    calls = []

    class HookedAgent(Agent):
        def review(self, run):
            calls.append("review")

        def after_run(self, run):
            calls.append("after_run")

    class AlwaysFail:
        def step(self, run):
            return Fail(error="nope")

    provider = FakeProvider(responses=[])
    Executor(provider, strategy=AlwaysFail()).run(HookedAgent(), Run(input="hi"))

    assert calls == ["after_run"]


def test_plan_is_not_re_run_when_resuming_a_paused_run():
    calls = []

    class HookedAgent(Agent):
        tools = []

        def plan(self, run):
            calls.append("plan")

    class SendEmail(Tool):
        requires_approval = True

        def call(self, to: str) -> str:
            return f"sent to {to}"

    class SupportAgent(HookedAgent):
        tools = [SendEmail]

    provider = FakeProvider(
        responses=[
            Message(
                role=Role.ASSISTANT,
                tool_calls=[ToolCall(name="SendEmail", arguments={"to": "a@b.com"})],
            ),
            Message(role=Role.ASSISTANT, content="Email sent."),
        ]
    )
    executor = Executor(provider)
    agent = SupportAgent()
    run = Run(input="email someone")

    executor.run(agent, run)
    approve(run, run.tool_calls[0].id)
    executor.run(agent, run)

    assert calls == ["plan"]


def test_gated_tool_call_pauses_the_run_for_approval():
    class SendEmail(Tool):
        requires_approval = True

        def call(self, to: str) -> str:
            return f"sent to {to}"

    class SupportAgent(Agent):
        tools = [SendEmail]

    provider = FakeProvider(
        responses=[
            Message(
                role=Role.ASSISTANT,
                tool_calls=[ToolCall(name="SendEmail", arguments={"to": "a@b.com"})],
            )
        ]
    )
    executor = Executor(provider)
    run = Run(input="email someone")

    result = executor.run(SupportAgent(), run)

    assert result.status == RunStatus.AWAITING_APPROVAL
    assert len(provider.calls) == 1  # never got past the gate to call again
    pending = result.tool_calls[0]
    assert pending.approved is None
    assert not pending.completed


def test_approving_a_gated_tool_call_lets_the_run_finish():
    class SendEmail(Tool):
        requires_approval = True

        def call(self, to: str) -> str:
            return f"sent to {to}"

    class SupportAgent(Agent):
        tools = [SendEmail]

    provider = FakeProvider(
        responses=[
            Message(
                role=Role.ASSISTANT,
                tool_calls=[ToolCall(name="SendEmail", arguments={"to": "a@b.com"})],
            ),
            Message(role=Role.ASSISTANT, content="Email sent."),
        ]
    )
    executor = Executor(provider)
    agent = SupportAgent()
    run = Run(input="email someone")

    executor.run(agent, run)
    assert run.status == RunStatus.AWAITING_APPROVAL

    approve(run, run.tool_calls[0].id)
    result = executor.run(agent, run)

    assert result.status == RunStatus.COMPLETED
    assert result.result == "Email sent."
    assert result.tool_calls[0].result == "sent to a@b.com"


def test_tool_returning_an_artifact_records_it_on_the_run():
    class ExtractData(Tool):
        def call(self) -> DataArtifact:
            return DataArtifact(data={"score": 0.9})

    class ExtractAgent(Agent):
        tools = [ExtractData]

    provider = FakeProvider(
        responses=[
            Message(
                role=Role.ASSISTANT,
                tool_calls=[ToolCall(name="ExtractData", arguments={})],
            ),
            Message(role=Role.ASSISTANT, content="Extracted the score."),
        ]
    )
    executor = Executor(provider)
    run = Run(input="extract the score")

    result = executor.run(ExtractAgent(), run)

    assert result.status == RunStatus.COMPLETED
    assert len(result.artifacts) == 1
    artifact = result.artifacts[0]
    assert isinstance(artifact, DataArtifact)
    assert artifact.data == {"score": 0.9}

    tool_message = next(m for m in result.messages if m.role == Role.TOOL)
    assert tool_message.content == artifact.summary()

    assert EventType.ARTIFACT_CREATED in [e.type for e in result.events]


def test_strategy_protocol_is_satisfiable_without_inheritance():
    class AlwaysComplete:
        def step(self, run):
            return Complete(result="done")

    strategy: Strategy = AlwaysComplete()
    provider = FakeProvider(responses=[])
    result = Executor(provider, strategy=strategy).run(WeatherAgent(), Run(input="x"))

    assert result.status == RunStatus.COMPLETED
    assert result.result == "done"
