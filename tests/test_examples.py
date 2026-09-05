"""Runs the example scripts' Agent/logic against a FakeProvider.

Examples themselves call a live provider (see their docstrings), so these
tests import each script as a module (its `if __name__ == "__main__":` block
never executes on import) and drive the same Agent classes through
Executor/FakeProvider, to catch example rot without spending API credits.
"""

import asyncio
import importlib.util
from pathlib import Path
from typing import Any

import pytest

from runa import Executor, Judge, Run, RunStatus, approve, configure, run_evals
from runa.application import application
from runa.core import Message, Role, ToolCall
from tests.fakes import FakeAsyncProvider, FakeProvider, FakeStreamingProvider

EXAMPLES_DIR = Path(__file__).parent.parent / "examples"


def _load(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, EXAMPLES_DIR / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def _reset_default_provider(monkeypatch):
    monkeypatch.setattr(application.config, "provider", None)


def test_hello_example():
    hello = _load("hello")
    fake = FakeProvider(
        [
            Message(
                role=Role.ASSISTANT,
                tool_calls=[ToolCall(name="get_weather", arguments={"city": "Tokyo"})],
            ),
            Message(role=Role.ASSISTANT, content="It's sunny in Tokyo."),
        ]
    )
    configure(provider=fake)

    run = hello.WeatherAgent.run("What's the weather in Tokyo?")

    assert run.status == RunStatus.COMPLETED
    assert run.result == "It's sunny in Tokyo."


def test_hello_anthropic_example():
    hello_anthropic = _load("hello_anthropic")
    fake = FakeProvider(
        [
            Message(
                role=Role.ASSISTANT,
                tool_calls=[ToolCall(name="get_weather", arguments={"city": "Tokyo"})],
            ),
            Message(role=Role.ASSISTANT, content="It's sunny in Tokyo."),
        ]
    )
    configure(provider=fake)

    run = hello_anthropic.WeatherAgent.run("What's the weather in Tokyo?")

    assert run.status == RunStatus.COMPLETED
    assert run.result == "It's sunny in Tokyo."


def test_conversation_example():
    conversation_example = _load("conversation")
    fake = FakeProvider(
        [
            Message(role=Role.ASSISTANT, content="I'm sorry to hear that."),
            Message(role=Role.ASSISTANT, content="It was A123."),
        ]
    )
    configure(provider=fake)

    conversation = conversation_example.Conversation()
    first = conversation_example.SupportAgent.run(
        "My order #A123 hasn't arrived.", conversation=conversation
    )
    second = conversation_example.SupportAgent.run(
        "What was that order number again?", conversation=conversation
    )

    assert first.status == RunStatus.COMPLETED
    assert second.status == RunStatus.COMPLETED
    # second call's messages carry the first turn's history forward
    contents = [m.content for m in fake.calls[1]["messages"]]
    assert contents == [
        conversation_example.SupportAgent.instructions,
        "My order #A123 hasn't arrived.",
        "I'm sorry to hear that.",
        "What was that order number again?",
    ]


def test_background_example():
    background = _load("background")
    fake = FakeProvider(
        [
            Message(
                role=Role.ASSISTANT,
                tool_calls=[ToolCall(name="get_weather", arguments={"city": "Kyoto"})],
            ),
            Message(role=Role.ASSISTANT, content="It's sunny in Kyoto."),
        ]
    )
    configure(provider=fake)

    run = background.WeatherAgent.run_later("What's the weather in Kyoto?")

    assert run.status == RunStatus.COMPLETED
    assert run.result == "It's sunny in Kyoto."


def test_approval_example():
    approval = _load("approval")
    fake = FakeProvider(
        [
            Message(
                role=Role.ASSISTANT,
                tool_calls=[
                    ToolCall(
                        name="send_refund",
                        arguments={"order_id": "A123", "amount": 42.0},
                    )
                ],
            ),
            Message(role=Role.ASSISTANT, content="Refunded order A123."),
        ]
    )
    executor = Executor(provider=fake)
    agent = approval.SupportAgent()

    run = executor.run(agent, Run(input="Refund order A123 for $42."))
    assert run.status == RunStatus.AWAITING_APPROVAL

    pending = next(tc for tc in run.tool_calls if not tc.completed)
    approve(run, pending.id)
    run = executor.run(agent, run)

    assert run.status == RunStatus.COMPLETED
    assert run.result == "Refunded order A123."


def test_eval_example(monkeypatch):
    # module-level `OpenAIProvider()` construction requires a key to be
    # present at import time, even though it's swapped for a fake below.
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    eval_example = _load("eval")
    fake = FakeProvider(
        [
            Message(
                role=Role.ASSISTANT,
                tool_calls=[ToolCall(name="get_weather", arguments={"city": "Tokyo"})],
            ),
            Message(role=Role.ASSISTANT, content="Tokyo is sunny."),
            Message(role=Role.ASSISTANT, content="Kyoto is sunny."),
            Message(role=Role.ASSISTANT, content="Osaka is sunny."),
        ]
    )
    executor = Executor(provider=fake)
    agent = eval_example.WeatherAgent()
    # the module's `judge` is bound to a real OpenAIProvider at import time;
    # swap it for a fake so the "is a helpful answer" case stays offline too.
    eval_example.judge = Judge(
        FakeProvider([Message(role=Role.ASSISTANT, content="PASS")])
    )

    results = run_evals(agent, executor, eval_example.cases)

    assert all(result.passed for result in results), [
        (r.case.name, r.error) for r in results if not r.passed
    ]


def test_plan_and_review_example(monkeypatch):
    # module-level `OpenAIProvider()` construction requires a key to be
    # present at import time, even though it's swapped for a fake below.
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    plan_and_review = _load("plan_and_review")
    fake = FakeProvider(
        [
            Message(role=Role.ASSISTANT, content="1. search\n2. summarize"),
            Message(
                role=Role.ASSISTANT,
                tool_calls=[ToolCall(name="search", arguments={"query": "fusion"})],
            ),
            Message(role=Role.ASSISTANT, content="draft answer"),
            Message(role=Role.ASSISTANT, content="revised answer"),
        ]
    )
    # plan()/review() close over the module's `provider` global directly, so
    # it needs swapping the same way test_eval_example swaps `judge`.
    plan_and_review.provider = fake

    run = Executor(fake).run(plan_and_review.ResearchAgent(), Run(input="fusion?"))

    assert run.status == RunStatus.COMPLETED
    assert run.result == "revised answer"
    assert run.state.plan == "1. search\n2. summarize"
    assert len(run.artifacts) == 1


def test_streaming_example():
    streaming = _load("streaming")
    provider = FakeStreamingProvider(
        [
            Message(
                role=Role.ASSISTANT,
                tool_calls=[ToolCall(name="get_weather", arguments={"city": "Tokyo"})],
            ),
            Message(role=Role.ASSISTANT, content="Tokyo is sunny."),
        ]
    )
    seen: list[str] = []

    run = Executor(provider).run(
        streaming.WeatherAgent(),
        Run(input="What's the weather in Tokyo?"),
        on_chunk=lambda chunk: seen.append(chunk.delta),
    )

    assert run.status == RunStatus.COMPLETED
    assert run.result == "Tokyo is sunny."
    assert "".join(seen) == "Tokyo is sunny."


def test_delegate_example():
    delegate = _load("delegate")
    fake = FakeProvider(
        [
            Message(
                role=Role.ASSISTANT,
                tool_calls=[
                    ToolCall(
                        name="ResearchAgent",
                        arguments={"input": "fusion energy"},
                    )
                ],
            ),
            Message(role=Role.ASSISTANT, content="Fusion is making progress."),
            Message(role=Role.ASSISTANT, content="Fusion is making progress."),
        ]
    )
    configure(provider=fake)

    run = delegate.LeadAgent.run("What's promising about fusion energy?")

    assert run.status == RunStatus.COMPLETED
    assert run.result == "Fusion is making progress."


def test_parallel_delegate_example():
    parallel_delegate = _load("parallel_delegate")
    fake = FakeAsyncProvider(
        [
            Message(
                role=Role.ASSISTANT,
                tool_calls=[
                    ToolCall(name="WeatherAgent", arguments={"input": "Tokyo"}),
                    ToolCall(name="NewsAgent", arguments={"input": "Tokyo"}),
                ],
            ),
            Message(role=Role.ASSISTANT, content="Sunny, 22C."),
            Message(role=Role.ASSISTANT, content="Local team wins championship."),
            Message(role=Role.ASSISTANT, content="Sunny and 22C; the local team won."),
        ]
    )
    configure(provider=FakeProvider([]), async_provider=fake)

    run = asyncio.run(parallel_delegate.BriefingAgent.run_async("Tokyo"))

    assert run.status == RunStatus.COMPLETED
    assert run.result == "Sunny and 22C; the local team won."
