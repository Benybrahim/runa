import asyncio
import threading
import time

import pytest

from runa.agent import Agent
from runa.approval import approve
from runa.core import (
    DataArtifact,
    EffectStatus,
    EventType,
    Message,
    Role,
    Run,
    RunStatus,
    ToolCall,
)
from runa.runtime.driving import RunAlreadyDriving
from runa.runtime.driving import default_guard as driving_guard
from runa.runtime.executor import Executor
from runa.runtime.provider import RetryingProvider, StreamChunk
from runa.runtime.retry import RetryStrategy
from runa.runtime.strategy import CallModel, Complete, Strategy
from runa.tool import Tool
from tests.fakes import FakeProvider, FakeStreamingProvider


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

    result = asyncio.run(executor.run(agent, run))

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


def test_executor_runs_every_tool_call_requested_in_a_single_turn():
    provider = FakeProvider(
        responses=[
            Message(
                role=Role.ASSISTANT,
                tool_calls=[
                    ToolCall(name="GetWeather", arguments={"city": "Tokyo"}),
                    ToolCall(name="GetWeather", arguments={"city": "Osaka"}),
                ],
            ),
            Message(role=Role.ASSISTANT, content="Both are sunny."),
        ]
    )
    executor = Executor(provider)
    agent = WeatherAgent()
    run = Run(input="What's the weather in Tokyo and Osaka?")

    result = asyncio.run(executor.run(agent, run))

    assert result.status == RunStatus.COMPLETED
    assert result.result == "Both are sunny."
    tokyo, osaka = result.tool_calls
    assert tokyo.succeeded and tokyo.result == "Tokyo: sunny"
    assert osaka.succeeded and osaka.result == "Osaka: sunny"

    # both tool results are fed back before the model is asked again
    roles = [message.role for message in result.messages]
    assert roles == [
        Role.SYSTEM,
        Role.USER,
        Role.ASSISTANT,
        Role.TOOL,
        Role.TOOL,
        Role.ASSISTANT,
    ]
    assert len(provider.calls) == 2


def test_model_responded_event_carries_the_messages_usage():
    provider = FakeProvider(
        responses=[
            Message(
                role=Role.ASSISTANT,
                content="hi",
                usage={"input_tokens": 10, "output_tokens": 3},
            )
        ]
    )
    result = asyncio.run(Executor(provider).run(WeatherAgent(), Run(input="hello")))

    responded = next(e for e in result.events if e.type == EventType.MODEL_RESPONDED)
    assert responded.data["usage"] == {"input_tokens": 10, "output_tokens": 3}


def test_model_responded_event_usage_is_none_when_the_provider_reports_none():
    provider = FakeProvider(responses=[Message(role=Role.ASSISTANT, content="hi")])
    result = asyncio.run(Executor(provider).run(WeatherAgent(), Run(input="hello")))

    responded = next(e for e in result.events if e.type == EventType.MODEL_RESPONDED)
    assert responded.data["usage"] is None


def test_executor_answers_directly_without_tools():
    provider = FakeProvider(
        responses=[Message(role=Role.ASSISTANT, content="No tools needed.")]
    )
    result = asyncio.run(Executor(provider).run(WeatherAgent(), Run(input="hello")))

    assert result.status == RunStatus.COMPLETED
    assert result.result == "No tools needed."
    assert len(provider.calls) == 1


def test_executor_records_an_artifact_a_tool_returns():
    class ExtractData(Tool):
        async def call(self) -> DataArtifact:
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
    run = asyncio.run(
        Executor(provider).run(ExtractAgent(), Run(input="extract the score"))
    )

    assert run.status == RunStatus.COMPLETED
    assert len(run.artifacts) == 1
    artifact = run.artifacts[0]
    assert isinstance(artifact, DataArtifact)
    assert artifact.data == {"score": 0.9}

    tool_message = next(m for m in run.messages if m.role == Role.TOOL)
    assert tool_message.content == artifact.summary()
    assert EventType.ARTIFACT_CREATED in [e.type for e in run.events]


def test_tool_exception_fails_the_run():
    class BrokenTool(Tool):
        async def call(self) -> None:
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
    result = asyncio.run(Executor(provider).run(BrokenAgent(), Run(input="x")))

    assert result.status == RunStatus.FAILED
    assert "boom" in result.events[-1].data["error"]

    tool_failed = next(e for e in result.events if e.type == EventType.TOOL_FAILED)
    assert tool_failed.data["error"] == "boom"
    assert tool_failed.data["effect"] == "unknown"
    assert result.tool_calls[0].error == "boom"
    assert result.tool_calls[0].attempts == 1
    assert result.tool_calls[0].effect == EffectStatus.UNKNOWN


def test_a_hallucinated_tool_call_fails_the_run_with_a_clear_message():
    """A model calling a tool name not declared on the Agent used to fail the
    Run with just `str(KeyError("Ghost"))`, `"'Ghost'"`, with no indication
    it was even about a tool call. This should name the problem and list
    what *is* declared, so `run.error`/`runa runs show` are actually useful.
    """
    provider = FakeProvider(
        responses=[
            Message(
                role=Role.ASSISTANT,
                tool_calls=[ToolCall(name="Ghost", arguments={})],
            )
        ]
    )
    result = asyncio.run(Executor(provider).run(WeatherAgent(), Run(input="x")))

    assert result.status == RunStatus.FAILED
    assert "unknown tool 'Ghost'" in (result.error or "")
    assert "GetWeather" in (result.error or "")


def test_a_transient_model_error_fails_the_run_with_no_retrying_provider():
    class FlakyProvider:
        def __init__(self):
            self.attempts = 0

        async def complete(self, *, messages, tools, model):
            self.attempts += 1
            raise ConnectionError("rate limited")

    provider = FlakyProvider()
    result = asyncio.run(Executor(provider).run(WeatherAgent(), Run(input="hello")))

    assert result.status == RunStatus.FAILED
    assert "rate limited" in (result.error or "")
    assert provider.attempts == 1  # no retry at all without RetryingProvider


def test_retrying_provider_rescues_a_run_from_a_transient_model_error():
    class FlakyProvider:
        def __init__(self):
            self.attempts = 0

        async def complete(self, *, messages, tools, model):
            self.attempts += 1
            if self.attempts < 3:
                raise ConnectionError("rate limited")
            return Message(role=Role.ASSISTANT, content="hi")

    inner = FlakyProvider()
    provider = RetryingProvider(inner, max_retries=3, sleep=lambda s: asyncio.sleep(0))
    result = asyncio.run(Executor(provider).run(WeatherAgent(), Run(input="hello")))

    assert result.status == RunStatus.COMPLETED
    assert result.result == "hi"
    assert inner.attempts == 3


def test_retry_strategy_retries_a_flaky_tool_before_succeeding():
    class FlakyTool(Tool):
        idempotent = True
        calls = 0

        async def call(self) -> str:
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
    result = asyncio.run(executor.run(FlakyAgent(), Run(input="do the flaky thing")))

    assert result.status == RunStatus.COMPLETED
    assert result.result == "done"
    assert FlakyTool.calls == 3
    assert result.tool_calls[0].attempts == 3
    assert result.tool_calls[0].error is None
    assert result.tool_calls[0].effect == EffectStatus.OBSERVED


def test_retry_strategy_fails_after_exhausting_retries():
    class AlwaysBroken(Tool):
        idempotent = True

        async def call(self) -> None:
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
    result = asyncio.run(executor.run(BrokenAgent(), Run(input="do the thing")))

    assert result.status == RunStatus.FAILED
    assert "nope" in result.events[-1].data["error"]
    assert result.tool_calls[0].attempts == 3


def test_retry_strategy_does_not_retry_a_non_idempotent_tool():
    class ChargeCard(Tool):
        calls = 0

        async def call(self) -> None:
            ChargeCard.calls += 1
            raise RuntimeError("gateway timeout")

    class BillingAgent(Agent):
        tools = [ChargeCard]

    provider = FakeProvider(
        responses=[
            Message(
                role=Role.ASSISTANT,
                tool_calls=[ToolCall(name="ChargeCard", arguments={})],
            )
        ]
    )
    executor = Executor(provider, strategy=RetryStrategy(max_retries=3))
    result = asyncio.run(executor.run(BillingAgent(), Run(input="charge the customer")))

    assert result.status == RunStatus.FAILED
    assert "gateway timeout" in result.events[-1].data["error"]
    assert ChargeCard.calls == 1
    assert result.tool_calls[0].attempts == 1
    assert result.tool_calls[0].effect == EffectStatus.UNKNOWN


def test_max_steps_fails_the_run_instead_of_looping_forever():
    class NeverEndingStrategy:
        def step(self, run):
            return CallModel()

    provider = FakeProvider(
        responses=[Message(role=Role.ASSISTANT, content="ignored")] * 100
    )
    executor = Executor(provider, strategy=NeverEndingStrategy(), max_steps=3)
    result = asyncio.run(executor.run(WeatherAgent(), Run(input="loop forever")))

    assert result.status == RunStatus.FAILED
    assert "max_steps" in result.events[-1].data["error"]


def test_timeout_fails_the_run_instead_of_hanging_forever():
    class NeverEndingStrategy:
        def step(self, run):
            return CallModel()

    provider = FakeProvider(
        responses=[Message(role=Role.ASSISTANT, content="ignored")] * 100
    )
    executor = Executor(provider, strategy=NeverEndingStrategy(), timeout=0.0)
    result = asyncio.run(executor.run(WeatherAgent(), Run(input="loop forever")))

    assert result.status == RunStatus.FAILED
    assert "timeout" in result.events[-1].data["error"]


def test_timeout_does_not_interfere_with_a_normal_run():
    provider = FakeProvider(responses=[Message(role=Role.ASSISTANT, content="ok")])
    executor = Executor(provider, timeout=60)

    result = asyncio.run(executor.run(WeatherAgent(), Run(input="hi")))

    assert result.status == RunStatus.COMPLETED
    assert result.result == "ok"


def test_cancel_requested_before_the_loop_starts_stops_the_run_immediately():
    class CancellingAgent(WeatherAgent):
        def before_run(self, run):
            run.request_cancel()

    provider = FakeProvider(responses=[])
    result = asyncio.run(Executor(provider).run(CancellingAgent(), Run(input="hi")))

    assert result.status == RunStatus.CANCELLED
    assert result.events[-1].type == EventType.RUN_CANCELLED
    assert provider.calls == []


def test_cancel_requested_mid_loop_stops_the_run_at_the_next_checkpoint():
    class CancelOnSecondStep:
        def __init__(self):
            self.calls = 0

        def step(self, run):
            self.calls += 1
            if self.calls == 2:
                run.request_cancel()
            return CallModel()

    provider = FakeProvider(
        responses=[Message(role=Role.ASSISTANT, content="ignored")] * 5
    )
    strategy = CancelOnSecondStep()
    executor = Executor(provider, strategy=strategy)
    result = asyncio.run(executor.run(WeatherAgent(), Run(input="hi")))

    assert result.status == RunStatus.CANCELLED
    assert result.events[-1].type == EventType.RUN_CANCELLED
    # the step that requested cancellation still ran its own action to
    # completion; cancellation is honored at the *next* checkpoint, not
    # mid-action
    assert len(provider.calls) == 2
    assert strategy.calls == 2


def test_agent_hooks_are_called_around_execution():
    calls = []

    class HookedAgent(Agent):
        def before_run(self, run):
            calls.append("before_run")

        def after_run(self, run):
            calls.append("after_run")

    provider = FakeProvider(responses=[Message(role=Role.ASSISTANT, content="ok")])
    asyncio.run(Executor(provider).run(HookedAgent(), Run(input="hi")))

    assert calls == ["before_run", "after_run"]


def test_a_bug_in_before_run_fails_the_run_instead_of_crashing_and_stranding_it():
    # Before this, an exception here propagated straight out of
    # Executor.run() *and* left the Run stuck at RUNNING forever (run.start()
    # already ran), an ambiguous non-terminal state indistinguishable from a
    # Run still genuinely in progress.
    class BuggyAgent(Agent):
        def before_run(self, run):
            raise RuntimeError("bug in before_run")

    provider = FakeProvider(responses=[])
    run = Run(input="hi")

    result = asyncio.run(Executor(provider).run(BuggyAgent(), run))

    assert result.status == RunStatus.FAILED
    assert result.error == "bug in before_run"
    assert len(provider.calls) == 0  # never reached the step loop


def test_a_bug_while_seeding_the_run_fails_it_instead_of_stranding_it():
    # Before this, seed_run() ran *before* run.start(); an exception there
    # left the Run stuck at QUEUED forever (run.fail() from QUEUED is an
    # IllegalTransition) and propagated straight out of Executor.run()
    # uncaught. That's especially bad for run_later() on a background
    # thread, where nothing would ever observe the exception at all.
    class Unstringable:
        def __str__(self):
            raise RuntimeError("bug while rendering input")

    provider = FakeProvider(responses=[])
    run = Run(input=Unstringable())

    result = asyncio.run(Executor(provider).run(WeatherAgent(), run))

    assert result.status == RunStatus.FAILED
    assert "bug while rendering input" in (result.error or "")
    assert len(provider.calls) == 0  # never reached the step loop


def test_a_bug_in_after_run_does_not_crash_or_falsify_an_already_completed_run(
    recwarn,
):
    # The Run already reached its real terminal status by the time
    # after_run runs, so a bug there must not be turned into a Run failure
    # (that would misreport a Run that actually completed); it's surfaced
    # as a warning instead.
    class BuggyAgent(Agent):
        def after_run(self, run):
            raise RuntimeError("bug in after_run")

    provider = FakeProvider(responses=[Message(role=Role.ASSISTANT, content="ok")])
    run = Run(input="hi")

    result = asyncio.run(Executor(provider).run(BuggyAgent(), run))

    assert result.status == RunStatus.COMPLETED
    assert result.result == "ok"
    assert any("bug in after_run" in str(w.message) for w in recwarn.list)


def test_running_an_already_terminal_run_again_is_a_no_op():
    calls = []

    class HookedAgent(Agent):
        def after_run(self, run):
            calls.append("after_run")

    provider = FakeProvider(responses=[Message(role=Role.ASSISTANT, content="ok")])
    executor = Executor(provider)
    agent = HookedAgent()
    run = Run(input="hi")

    asyncio.run(executor.run(agent, run))
    assert calls == ["after_run"]
    assert len(provider.calls) == 1

    result = asyncio.run(executor.run(agent, run))

    assert result is run
    assert calls == ["after_run"]  # not called again
    assert len(provider.calls) == 1  # no second model call either


def test_run_raises_when_another_executor_is_already_driving_it():
    provider = FakeProvider(responses=[])
    executor = Executor(provider)
    run = Run(input="hi")
    driving_guard.begin(run.id)  # simulate another Executor already in flight
    try:
        with pytest.raises(RunAlreadyDriving):
            asyncio.run(executor.run(WeatherAgent(), run))
    finally:
        driving_guard.end(run.id)

    # the guard fires before any seeding/model call, so nothing ran
    assert provider.calls == []
    assert run.status == RunStatus.CREATED


def test_two_threads_driving_the_same_run_do_not_silently_corrupt_it():
    """Reproduces the real hazard `begin_driving()` closes: two Executors
    racing the same Run object used to interleave their steps with no
    error, silently duplicating the model call. Now exactly one thread
    succeeds and the other gets a clear `RunAlreadyDriving`."""

    class SlowProvider:
        def __init__(self):
            self.calls = 0

        async def complete(self, *, messages, tools, model):
            self.calls += 1
            await asyncio.sleep(0.1)
            return Message(role=Role.ASSISTANT, content="done")

    provider = SlowProvider()
    executor = Executor(provider)
    run = Run(input="hi")
    agent = WeatherAgent()
    results: list[Run] = []
    errors: list[Exception] = []

    def drive():
        try:
            results.append(asyncio.run(executor.run(agent, run)))
        except RunAlreadyDriving as exc:
            errors.append(exc)

    threads = [threading.Thread(target=drive) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(errors) == 1
    assert len(results) == 1
    assert results[0].status == RunStatus.COMPLETED
    assert provider.calls == 1
    assert [m.role for m in run.messages].count(Role.ASSISTANT) == 1


def test_before_run_is_not_re_run_when_resuming_a_paused_run():
    calls = []

    class HookedAgent(Agent):
        tools = []

        def before_run(self, run):
            calls.append("before_run")

    class SendEmail(Tool):
        requires_approval = True

        async def call(self, to: str) -> str:
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

    asyncio.run(executor.run(agent, run))
    approve(run, run.tool_calls[0].id)
    asyncio.run(executor.run(agent, run))

    assert calls == ["before_run"]


def test_gated_tool_call_pauses_the_run_for_approval():
    class SendEmail(Tool):
        requires_approval = True

        async def call(self, to: str) -> str:
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
    result = asyncio.run(Executor(provider).run(SupportAgent(), Run(input="x")))

    assert result.status == RunStatus.AWAITING_APPROVAL
    assert len(provider.calls) == 1  # never got past the gate to call again
    pending = result.tool_calls[0]
    assert pending.approved is None
    assert not pending.succeeded


def test_runnable_siblings_execute_while_a_gated_call_blocks_the_batch():
    class SendEmail(Tool):
        requires_approval = True

        async def call(self, to: str) -> str:
            return f"sent to {to}"

    class GetWeatherAsync(Tool):
        async def call(self, city: str) -> str:
            return f"{city}: sunny"

    class MixedAgent(Agent):
        tools = [SendEmail, GetWeatherAsync]

    provider = FakeProvider(
        responses=[
            Message(
                role=Role.ASSISTANT,
                tool_calls=[
                    ToolCall(name="SendEmail", arguments={"to": "a@b.com"}),
                    ToolCall(name="GetWeatherAsync", arguments={"city": "Kyoto"}),
                ],
            )
        ]
    )
    run = asyncio.run(Executor(provider).run(MixedAgent(), Run(input="x")))

    assert run.status == RunStatus.AWAITING_APPROVAL
    send_email_call = next(tc for tc in run.tool_calls if tc.name == "SendEmail")
    weather_call = next(tc for tc in run.tool_calls if tc.name == "GetWeatherAsync")
    assert not send_email_call.succeeded
    assert weather_call.succeeded
    assert weather_call.result == "Kyoto: sunny"


def test_approving_a_gated_tool_call_lets_the_run_finish():
    class SendEmail(Tool):
        requires_approval = True

        async def call(self, to: str) -> str:
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
    run = asyncio.run(executor.run(agent, Run(input="email someone")))
    assert run.status == RunStatus.AWAITING_APPROVAL

    approve(run, run.tool_calls[0].id)
    result = asyncio.run(executor.run(agent, run))

    assert result.status == RunStatus.COMPLETED
    assert result.result == "Email sent."
    assert result.tool_calls[0].result == "sent to a@b.com"


def test_approving_gated_calls_one_at_a_time_eventually_runs_them_all():
    class SendEmail(Tool):
        requires_approval = True

        async def call(self, to: str) -> str:
            return f"emailed {to}"

    class SendSms(Tool):
        requires_approval = True

        async def call(self, to: str) -> str:
            return f"texted {to}"

    class SupportAgent(Agent):
        tools = [SendEmail, SendSms]

    provider = FakeProvider(
        responses=[
            Message(
                role=Role.ASSISTANT,
                tool_calls=[
                    ToolCall(name="SendEmail", arguments={"to": "a@b.com"}),
                    ToolCall(name="SendSms", arguments={"to": "555"}),
                ],
            ),
            Message(role=Role.ASSISTANT, content="done"),
        ]
    )
    executor = Executor(provider)
    agent = SupportAgent()
    run = asyncio.run(executor.run(agent, Run(input="notify someone")))
    assert run.status == RunStatus.AWAITING_APPROVAL

    email_call = next(tc for tc in run.tool_calls if tc.name == "SendEmail")
    approve(run, email_call.id)
    run = asyncio.run(executor.run(agent, run))
    assert run.status == RunStatus.AWAITING_APPROVAL  # SendSms still gated

    sms_call = next(tc for tc in run.tool_calls if tc.name == "SendSms")
    approve(run, sms_call.id)
    run = asyncio.run(executor.run(agent, run))

    assert run.status == RunStatus.COMPLETED
    assert run.result == "done"
    assert email_call.succeeded and email_call.result == "emailed a@b.com"
    assert sms_call.succeeded and sms_call.result == "texted 555"


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
    result = asyncio.run(
        Executor(provider).run(ExtractAgent(), Run(input="extract the score"))
    )

    assert result.status == RunStatus.COMPLETED
    assert len(result.artifacts) == 1
    artifact = result.artifacts[0]
    assert isinstance(artifact, DataArtifact)
    assert artifact.data == {"score": 0.9}

    tool_message = next(m for m in result.messages if m.role == Role.TOOL)
    assert tool_message.content == artifact.summary()

    assert EventType.ARTIFACT_CREATED in [e.type for e in result.events]


def test_on_chunk_receives_deltas_and_the_run_completes_normally():
    provider = FakeStreamingProvider(
        responses=[Message(role=Role.ASSISTANT, content="hi there")]
    )
    chunks: list[StreamChunk] = []

    result = asyncio.run(
        Executor(provider).run(
            WeatherAgent(), Run(input="hello"), on_chunk=chunks.append
        )
    )

    assert "".join(c.text for c in chunks) == "hi there"
    assert result.status == RunStatus.COMPLETED
    assert result.result == "hi there"


def test_on_chunk_streams_every_model_call_in_a_tool_use_loop():
    provider = FakeStreamingProvider(
        responses=[
            Message(
                role=Role.ASSISTANT,
                tool_calls=[ToolCall(name="GetWeather", arguments={"city": "Tokyo"})],
            ),
            Message(role=Role.ASSISTANT, content="Tokyo is sunny."),
        ]
    )
    chunks: list[StreamChunk] = []

    result = asyncio.run(
        Executor(provider).run(
            WeatherAgent(), Run(input="weather in Tokyo?"), on_chunk=chunks.append
        )
    )

    assert "".join(c.text for c in chunks) == "Tokyo is sunny."
    assert result.result == "Tokyo is sunny."


def test_on_chunk_accepts_an_async_callback():
    provider = FakeStreamingProvider(
        responses=[Message(role=Role.ASSISTANT, content="hi")]
    )
    chunks: list[StreamChunk] = []

    async def on_chunk(chunk: StreamChunk) -> None:
        await asyncio.sleep(0)
        chunks.append(chunk)

    result = asyncio.run(
        Executor(provider).run(WeatherAgent(), Run(input="hi"), on_chunk=on_chunk)
    )

    assert "".join(c.text for c in chunks) == "hi"
    assert result.result == "hi"


def test_on_chunk_requires_a_streaming_capable_provider():
    # like any other exception raised while applying an action, this is
    # caught and turned into a failed Run rather than propagating.
    provider = FakeProvider(responses=[])

    result = asyncio.run(
        Executor(provider).run(WeatherAgent(), Run(input="hi"), on_chunk=lambda c: None)
    )

    assert result.status == RunStatus.FAILED
    assert "StreamingProvider" in result.events[-1].data["error"]


def test_strategy_protocol_is_satisfiable_without_inheritance():
    class AlwaysComplete:
        def step(self, run):
            return Complete(result="done")

    strategy: Strategy = AlwaysComplete()
    provider = FakeProvider(responses=[])
    result = asyncio.run(
        Executor(provider, strategy=strategy).run(WeatherAgent(), Run(input="x"))
    )

    assert result.status == RunStatus.COMPLETED
    assert result.result == "done"


def test_parent_run_aware_tool_is_bound_before_it_is_called():
    class RecordsParent(Tool):
        def __init__(self) -> None:
            self.seen_parent_run_id: str | None = None

        def bind_parent_run_id(self, run_id: str) -> None:
            self.seen_parent_run_id = run_id

        def call(self) -> str:
            return self.seen_parent_run_id or "unbound"

    recorder = RecordsParent()

    class RecordingAgent(Agent):
        tools = [recorder]

    provider = FakeProvider(
        responses=[
            Message(
                role=Role.ASSISTANT,
                tool_calls=[ToolCall(name="RecordsParent", arguments={})],
            ),
            Message(role=Role.ASSISTANT, content="done"),
        ]
    )
    run = Run(input="x")

    result = asyncio.run(Executor(provider).run(RecordingAgent(), run))

    assert result.status == RunStatus.COMPLETED
    assert recorder.seen_parent_run_id == run.id


def test_independent_tool_calls_run_concurrently():
    class SlowToolA(Tool):
        async def call(self) -> str:
            await asyncio.sleep(0.2)
            return "a done"

    class SlowToolB(Tool):
        async def call(self) -> str:
            await asyncio.sleep(0.2)
            return "b done"

    class FanOutAgent(Agent):
        tools = [SlowToolA, SlowToolB]

    provider = FakeProvider(
        responses=[
            Message(
                role=Role.ASSISTANT,
                tool_calls=[
                    ToolCall(name="SlowToolA", arguments={}),
                    ToolCall(name="SlowToolB", arguments={}),
                ],
            ),
            Message(role=Role.ASSISTANT, content="both done"),
        ]
    )
    executor = Executor(provider)

    start = time.monotonic()
    run = asyncio.run(executor.run(FanOutAgent(), Run(input="do both")))
    elapsed = time.monotonic() - start

    assert run.status == RunStatus.COMPLETED
    # sequential execution would take >= 0.4s; concurrent stays close to 0.2s
    assert elapsed < 0.35, f"tool calls did not run concurrently (took {elapsed}s)"


def test_sync_tool_runs_via_to_thread_under_executor():
    provider = FakeProvider(
        responses=[
            Message(
                role=Role.ASSISTANT,
                tool_calls=[ToolCall(name="GetWeather", arguments={"city": "Osaka"})],
            ),
            Message(role=Role.ASSISTANT, content="Osaka is sunny."),
        ]
    )
    run = asyncio.run(Executor(provider).run(WeatherAgent(), Run(input="x")))

    assert run.status == RunStatus.COMPLETED
    assert run.tool_calls[0].result == "Osaka: sunny"


def test_transfer_alongside_sibling_tool_calls_fails_the_run():
    """A transfer=true delegation can't compose with concurrent siblings from
    the same turn (see `Executor._call_tools`'s docstring): whichever
    agent's tools the siblings belong to becomes ambiguous once control has
    moved, so the run fails with a clear error instead of running anything.
    """

    class SupportAgent(Agent):
        pass

    class GetWeatherAsync(Tool):
        async def call(self, city: str) -> str:
            return f"{city}: sunny"

    class TriageAgent(Agent):
        tools = [GetWeatherAsync]
        delegations = [SupportAgent]

    provider = FakeProvider(
        responses=[
            Message(
                role=Role.ASSISTANT,
                tool_calls=[
                    ToolCall(
                        name="SupportAgent",
                        arguments={"input": "x", "transfer": True},
                    ),
                    ToolCall(name="GetWeatherAsync", arguments={"city": "Kyoto"}),
                ],
            )
        ]
    )
    run = asyncio.run(Executor(provider).run(TriageAgent(), Run(input="x")))

    assert run.status == RunStatus.FAILED
    assert "transfer" in (run.error or "")
