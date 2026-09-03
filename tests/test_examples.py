"""Runs the example scripts' Agent/logic against a FakeProvider.

Examples themselves call a live provider (see their docstrings), so these
tests import each script as a module (its `if __name__ == "__main__":` block
never executes on import) and drive the same Agent classes through
Executor/FakeProvider, to catch example rot without spending API credits.
"""

import importlib.util
from pathlib import Path

import pytest

from runa import Executor, Judge, Run, RunStatus, approve, configure, run_evals
from runa.core import Message, Role, ToolCall
from tests.fakes import FakeProvider

EXAMPLES_DIR = Path(__file__).parent.parent / "examples"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, EXAMPLES_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def _reset_default_provider(monkeypatch):
    monkeypatch.setattr("runa.config._default_provider", None)


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


def test_eval_example():
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
    # the module's `judge` is bound to a real OpenAIProvider at import time —
    # swap it for a fake so the "is a helpful answer" case stays offline too.
    eval_example.judge = Judge(
        FakeProvider([Message(role=Role.ASSISTANT, content="PASS")])
    )

    results = run_evals(agent, executor, eval_example.cases)

    assert all(result.passed for result in results), [
        (r.case.name, r.error) for r in results if not r.passed
    ]


def test_plan_and_review_example():
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
