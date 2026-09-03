import asyncio
import time

from runa.agent import Agent
from runa.approval import approve
from runa.config import configure
from runa.core import DataArtifact, EventType, Message, Role, Run, RunStatus, ToolCall
from runa.runtime.async_executor import AsyncExecutor
from runa.runtime.executor import Executor
from runa.runtime.provider import StreamChunk
from runa.runtime.retry import RetryStrategy
from runa.runtime.strategy import CallModel
from runa.tool import Tool
from tests.fakes import (
    FakeAsyncProvider,
    FakeAsyncStreamingProvider,
    FakeProvider,
)


class GetWeather(Tool):
    def call(self, city: str) -> str:
        return f"{city}: sunny"


class WeatherAgent(Agent):
    instructions = "Answer weather questions."
    tools = [GetWeather]


def test_async_executor_runs_a_full_tool_use_loop():
    provider = FakeAsyncProvider(
        responses=[
            Message(
                role=Role.ASSISTANT,
                tool_calls=[ToolCall(name="GetWeather", arguments={"city": "Tokyo"})],
            ),
            Message(role=Role.ASSISTANT, content="Tokyo is sunny."),
        ]
    )
    executor = AsyncExecutor(provider)
    run = asyncio.run(executor.run(WeatherAgent(), Run(input="weather in Tokyo?")))

    assert run.status == RunStatus.COMPLETED
    assert run.result == "Tokyo is sunny."
    assert len(provider.calls) == 2

    event_types = [event.type for event in run.events]
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


def test_async_populated_context_is_seeded_as_a_system_message():
    provider = FakeAsyncProvider(responses=[Message(role=Role.ASSISTANT, content="ok")])
    executor = AsyncExecutor(provider)
    agent = WeatherAgent()
    run = Run(input="hello")
    run.context.resources = ["policy: refunds within 30 days"]

    result = asyncio.run(executor.run(agent, run))

    system_messages = [m.content for m in result.messages if m.role == Role.SYSTEM]
    assert system_messages[0] == "Answer weather questions."
    assert "resources: ['policy: refunds within 30 days']" in system_messages[1]


def test_async_executor_answers_directly_without_tools():
    provider = FakeAsyncProvider(
        responses=[Message(role=Role.ASSISTANT, content="No tools needed.")]
    )
    executor = AsyncExecutor(provider)
    run = asyncio.run(executor.run(WeatherAgent(), Run(input="hello")))

    assert run.status == RunStatus.COMPLETED
    assert run.result == "No tools needed."


def test_async_executor_records_an_artifact_a_tool_returns():
    class ExtractData(Tool):
        async def call(self) -> DataArtifact:
            return DataArtifact(data={"score": 0.9})

    class ExtractAgent(Agent):
        tools = [ExtractData]

    provider = FakeAsyncProvider(
        responses=[
            Message(
                role=Role.ASSISTANT,
                tool_calls=[ToolCall(name="ExtractData", arguments={})],
            ),
            Message(role=Role.ASSISTANT, content="Extracted the score."),
        ]
    )
    executor = AsyncExecutor(provider)
    run = asyncio.run(executor.run(ExtractAgent(), Run(input="extract the score")))

    assert len(run.artifacts) == 1
    artifact = run.artifacts[0]
    assert isinstance(artifact, DataArtifact)
    tool_message = next(m for m in run.messages if m.role == Role.TOOL)
    assert tool_message.content == artifact.summary()


def test_async_timeout_fails_the_run_instead_of_hanging_forever():
    class NeverEndingStrategy:
        def step(self, run):
            return CallModel()

    provider = FakeAsyncProvider(
        responses=[Message(role=Role.ASSISTANT, content="ignored")] * 100
    )
    executor = AsyncExecutor(provider, strategy=NeverEndingStrategy(), timeout=0.0)

    run = asyncio.run(executor.run(WeatherAgent(), Run(input="loop forever")))

    assert run.status == RunStatus.FAILED
    assert "timeout" in run.events[-1].data["error"]


def test_cancel_requested_before_the_loop_starts_stops_the_run_immediately():
    class CancellingAgent(WeatherAgent):
        def before_run(self, run):
            run.request_cancel()

    provider = FakeAsyncProvider(responses=[])
    executor = AsyncExecutor(provider)

    run = asyncio.run(executor.run(CancellingAgent(), Run(input="hi")))

    assert run.status == RunStatus.CANCELLED
    assert run.events[-1].type == EventType.RUN_CANCELLED
    assert provider.calls == []


def test_running_an_already_terminal_run_again_is_a_no_op():
    calls = []

    class HookedAgent(Agent):
        def after_run(self, run):
            calls.append("after_run")

    provider = FakeAsyncProvider(responses=[Message(role=Role.ASSISTANT, content="ok")])
    executor = AsyncExecutor(provider)
    agent = HookedAgent()
    run = Run(input="hi")

    asyncio.run(executor.run(agent, run))
    assert calls == ["after_run"]
    assert len(provider.calls) == 1

    result = asyncio.run(executor.run(agent, run))

    assert result is run
    assert calls == ["after_run"]
    assert len(provider.calls) == 1


def test_async_executor_review_hook_can_revise_the_result():
    class ReviewingAgent(Agent):
        def review(self, run):
            return f"revised: {run.messages[-1].content}"

    provider = FakeAsyncProvider(
        responses=[Message(role=Role.ASSISTANT, content="draft")]
    )

    run = asyncio.run(AsyncExecutor(provider).run(ReviewingAgent(), Run(input="hi")))

    assert run.result == "revised: draft"


def test_async_on_chunk_receives_deltas_and_the_run_completes_normally():
    provider = FakeAsyncStreamingProvider(
        responses=[Message(role=Role.ASSISTANT, content="hi there")]
    )
    chunks: list[StreamChunk] = []

    run = asyncio.run(
        AsyncExecutor(provider).run(
            WeatherAgent(), Run(input="hello"), on_chunk=chunks.append
        )
    )

    assert "".join(c.delta for c in chunks) == "hi there"
    assert run.status == RunStatus.COMPLETED
    assert run.result == "hi there"


def test_async_on_chunk_accepts_an_async_callback():
    provider = FakeAsyncStreamingProvider(
        responses=[Message(role=Role.ASSISTANT, content="hi")]
    )
    chunks: list[StreamChunk] = []

    async def on_chunk(chunk: StreamChunk) -> None:
        await asyncio.sleep(0)
        chunks.append(chunk)

    run = asyncio.run(
        AsyncExecutor(provider).run(WeatherAgent(), Run(input="hi"), on_chunk=on_chunk)
    )

    assert "".join(c.delta for c in chunks) == "hi"
    assert run.result == "hi"


def test_async_on_chunk_requires_a_streaming_capable_provider():
    provider = FakeAsyncProvider(responses=[])

    run = asyncio.run(
        AsyncExecutor(provider).run(
            WeatherAgent(), Run(input="hi"), on_chunk=lambda c: None
        )
    )

    assert run.status == RunStatus.FAILED
    assert "AsyncStreamingProvider" in run.events[-1].data["error"]


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

    provider = FakeAsyncProvider(
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
    executor = AsyncExecutor(provider)

    start = time.monotonic()
    run = asyncio.run(executor.run(FanOutAgent(), Run(input="do both")))
    elapsed = time.monotonic() - start

    assert run.status == RunStatus.COMPLETED
    # sequential execution would take >= 0.4s; concurrent stays close to 0.2s
    assert elapsed < 0.35, f"tool calls did not run concurrently (took {elapsed}s)"


def test_sync_tool_runs_via_to_thread_under_async_executor():
    provider = FakeAsyncProvider(
        responses=[
            Message(
                role=Role.ASSISTANT,
                tool_calls=[ToolCall(name="GetWeather", arguments={"city": "Osaka"})],
            ),
            Message(role=Role.ASSISTANT, content="Osaka is sunny."),
        ]
    )
    run = asyncio.run(AsyncExecutor(provider).run(WeatherAgent(), Run(input="x")))

    assert run.status == RunStatus.COMPLETED
    assert run.tool_calls[0].result == "Osaka: sunny"


def test_tool_exception_fails_the_run():
    class BrokenTool(Tool):
        async def call(self) -> None:
            raise RuntimeError("boom")

    class BrokenAgent(Agent):
        tools = [BrokenTool]

    provider = FakeAsyncProvider(
        responses=[
            Message(
                role=Role.ASSISTANT,
                tool_calls=[ToolCall(name="BrokenTool", arguments={})],
            )
        ]
    )
    run = asyncio.run(AsyncExecutor(provider).run(BrokenAgent(), Run(input="x")))

    assert run.status == RunStatus.FAILED
    assert result_error(run) == "boom"
    assert run.tool_calls[0].attempts == 1


def result_error(run: Run) -> str:
    return run.events[-1].data["error"]


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

    provider = FakeAsyncProvider(
        responses=[
            Message(
                role=Role.ASSISTANT,
                tool_calls=[ToolCall(name="FlakyTool", arguments={})],
            ),
            Message(role=Role.ASSISTANT, content="done"),
        ]
    )
    executor = AsyncExecutor(provider, strategy=RetryStrategy(max_retries=3))
    run = asyncio.run(executor.run(FlakyAgent(), Run(input="x")))

    assert run.status == RunStatus.COMPLETED
    assert FlakyTool.calls == 3
    assert run.tool_calls[0].attempts == 3
    assert run.tool_calls[0].error is None


def test_gated_tool_call_pauses_the_run_for_approval():
    class SendEmail(Tool):
        requires_approval = True

        async def call(self, to: str) -> str:
            return f"sent to {to}"

    class SupportAgent(Agent):
        tools = [SendEmail]

    provider = FakeAsyncProvider(
        responses=[
            Message(
                role=Role.ASSISTANT,
                tool_calls=[ToolCall(name="SendEmail", arguments={"to": "a@b.com"})],
            )
        ]
    )
    run = asyncio.run(AsyncExecutor(provider).run(SupportAgent(), Run(input="x")))

    assert run.status == RunStatus.AWAITING_APPROVAL
    assert not run.tool_calls[0].completed


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

    provider = FakeAsyncProvider(
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
    run = asyncio.run(AsyncExecutor(provider).run(MixedAgent(), Run(input="x")))

    assert run.status == RunStatus.AWAITING_APPROVAL
    send_email_call = next(tc for tc in run.tool_calls if tc.name == "SendEmail")
    weather_call = next(tc for tc in run.tool_calls if tc.name == "GetWeatherAsync")
    assert not send_email_call.completed
    assert weather_call.completed
    assert weather_call.result == "Kyoto: sunny"


def test_approving_a_gated_tool_call_lets_the_run_finish():
    class SendEmail(Tool):
        requires_approval = True

        async def call(self, to: str) -> str:
            return f"sent to {to}"

    class SupportAgent(Agent):
        tools = [SendEmail]

    provider = FakeAsyncProvider(
        responses=[
            Message(
                role=Role.ASSISTANT,
                tool_calls=[ToolCall(name="SendEmail", arguments={"to": "a@b.com"})],
            ),
            Message(role=Role.ASSISTANT, content="Email sent."),
        ]
    )
    executor = AsyncExecutor(provider)
    agent = SupportAgent()
    run = asyncio.run(executor.run(agent, Run(input="x")))
    assert run.status == RunStatus.AWAITING_APPROVAL

    approve(run, run.tool_calls[0].id)
    run = asyncio.run(executor.run(agent, run))

    assert run.status == RunStatus.COMPLETED
    assert run.result == "Email sent."


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

    provider = FakeAsyncProvider(
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
    executor = AsyncExecutor(provider)
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
    assert email_call.completed and email_call.result == "emailed a@b.com"
    assert sms_call.completed and sms_call.result == "texted 555"


def test_sync_executor_rejects_a_tool_with_an_async_call():
    class AsyncOnlyTool(Tool):
        async def call(self) -> str:
            return "nope"

    class BrokenAgent(Agent):
        tools = [AsyncOnlyTool]

    provider = FakeProvider(
        responses=[
            Message(
                role=Role.ASSISTANT,
                tool_calls=[ToolCall(name="AsyncOnlyTool", arguments={})],
            )
        ]
    )
    run = Executor(provider).run(BrokenAgent(), Run(input="x"))

    # Executor converts the TypeError into a failed Run rather than crashing,
    # same as any other exception raised while applying an Action.
    assert run.status == RunStatus.FAILED
    assert "AsyncExecutor" in run.events[-1].data["error"]


def test_run_async_uses_the_app_default_async_provider():
    class SimpleAgent(Agent):
        pass

    configure(
        provider=FakeProvider([]),
        async_provider=FakeAsyncProvider([Message(role=Role.ASSISTANT, content="hi")]),
    )

    run = asyncio.run(SimpleAgent.run_async("hello"))

    assert run.status == RunStatus.COMPLETED
    assert run.result == "hi"
