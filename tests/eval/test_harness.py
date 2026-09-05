import pytest

from runa.agent import Agent
from runa.core import Message, Role, Run, ToolCall
from runa.eval import (
    RUBRIC_GOAL,
    RUBRIC_HELPFUL,
    EvalCase,
    ExpectationFailed,
    Judge,
    expect,
    run_evals,
)
from runa.runtime import Executor
from runa.tool import Tool
from tests.fakes import FakeProvider


class GetWeather(Tool):
    def call(self, city: str) -> str:
        return f"{city}: sunny"


class WeatherAgent(Agent):
    instructions = "Answer weather questions."
    tools = [GetWeather]


def test_expect_to_be_completed_passes_on_a_completed_run():
    provider = FakeProvider(responses=[Message(role=Role.ASSISTANT, content="hi")])
    run = Executor(provider).run(WeatherAgent(), Run(input="hello"))

    expect(run).to_be_completed().to_have_result("hi").to_contain("hi")


def test_expect_to_be_completed_fails_on_a_failed_run():
    class BrokenTool(Tool):
        def call(self) -> None:
            raise RuntimeError("boom")

    class BrokenAgent(Agent):
        tools = [BrokenTool]

    provider = FakeProvider(
        responses=[
            Message(role=Role.ASSISTANT, tool_calls=[ToolCall(name="BrokenTool")])
        ]
    )
    run = Executor(provider).run(BrokenAgent(), Run(input="do it"))

    try:
        expect(run).to_be_completed()
    except ExpectationFailed as exc:
        assert "failed" in str(exc)
        assert "boom" in str(exc)
    else:
        raise AssertionError("expected ExpectationFailed")


def test_expect_to_have_error_passes_when_the_error_matches():
    run = Run(input="do it")
    run.start()
    run.fail("boom: connection refused")

    expect(run).to_have_error("connection refused")


def test_expect_to_have_error_fails_when_the_error_does_not_match():
    run = Run(input="do it")
    run.start()
    run.fail("boom")

    with pytest.raises(ExpectationFailed, match="connection refused"):
        expect(run).to_have_error("connection refused")


def test_expect_to_have_error_fails_when_the_run_never_failed():
    run = Run(input="do it")
    run.start()
    run.complete(result="done")

    with pytest.raises(ExpectationFailed):
        expect(run).to_have_error("connection refused")


def test_expect_to_have_called_checks_tool_calls():
    provider = FakeProvider(
        responses=[
            Message(
                role=Role.ASSISTANT,
                tool_calls=[ToolCall(name="GetWeather", arguments={"city": "Tokyo"})],
            ),
            Message(role=Role.ASSISTANT, content="Tokyo is sunny."),
        ]
    )
    run = Executor(provider).run(WeatherAgent(), Run(input="weather in Tokyo?"))

    expect(run).to_have_called("GetWeather")


def test_run_evals_reports_pass_and_fail_for_each_case():
    cases = [
        EvalCase(
            name="says hi",
            input="hello",
            check=lambda run: expect(run).to_be_completed().to_contain("hi"),
        ),
        EvalCase(
            name="wrong expectation",
            input="hello",
            check=lambda run: expect(run).to_contain("goodbye"),
        ),
    ]
    provider = FakeProvider(
        responses=[
            Message(role=Role.ASSISTANT, content="hi"),
            Message(role=Role.ASSISTANT, content="hi"),
        ]
    )
    executor = Executor(provider)

    results = run_evals(WeatherAgent(), executor, cases)

    assert len(results) == 2
    assert results[0].passed is True
    assert results[0].error is None
    assert results[1].passed is False
    assert "goodbye" in (results[1].error or "")


def test_to_satisfy_passes_when_judge_returns_pass():
    run = Run(input="what's the capital of France?")
    run.add_message(Message(role=Role.ASSISTANT, content="Paris."))
    provider = FakeProvider(responses=[Message(role=Role.ASSISTANT, content="PASS")])
    judge = Judge(provider)

    expect(run).to_satisfy("answers the question", judge=judge)


def test_to_satisfy_raises_when_judge_returns_fail():
    run = Run(input="what's the capital of France?")
    run.add_message(Message(role=Role.ASSISTANT, content="I don't know."))
    judge = Judge(
        FakeProvider(
            responses=[Message(role=Role.ASSISTANT, content="FAIL\nnever answers")]
        )
    )

    with pytest.raises(ExpectationFailed, match="never answers"):
        expect(run).to_satisfy("answers the question", judge=judge)


def test_to_be_helpful_grades_against_the_helpful_rubric():
    run = Run(input="what's the capital of France?")
    run.add_message(Message(role=Role.ASSISTANT, content="Paris."))
    provider = FakeProvider(responses=[Message(role=Role.ASSISTANT, content="PASS")])

    expect(run).to_be_helpful(judge=Judge(provider))

    assert RUBRIC_HELPFUL in provider.calls[0]["messages"][0].content


def test_to_meet_the_goal_grades_against_the_goal_rubric():
    run = Run(input="what's the capital of France?")
    run.add_message(Message(role=Role.ASSISTANT, content="Paris."))
    provider = FakeProvider(responses=[Message(role=Role.ASSISTANT, content="PASS")])

    expect(run).to_meet_the_goal(judge=Judge(provider))

    assert RUBRIC_GOAL in provider.calls[0]["messages"][0].content


def test_to_meet_the_goal_fails_when_the_judge_returns_fail():
    run = Run(input="book me a flight to Tokyo")
    run.add_message(Message(role=Role.ASSISTANT, content="I can help with that!"))
    judge = Judge(
        FakeProvider(
            responses=[
                Message(role=Role.ASSISTANT, content="FAIL\nno flight was booked")
            ]
        )
    )

    with pytest.raises(ExpectationFailed, match="no flight was booked"):
        expect(run).to_meet_the_goal(judge=judge)


def test_run_evals_runs_every_case_even_after_a_failure():
    cases = [
        EvalCase(name="a", input="x", check=lambda run: expect(run).to_contain("z")),
        EvalCase(name="b", input="y", check=lambda run: expect(run).to_be_completed()),
    ]
    provider = FakeProvider(
        responses=[
            Message(role=Role.ASSISTANT, content="hi"),
            Message(role=Role.ASSISTANT, content="hi"),
        ]
    )
    executor = Executor(provider)

    results = run_evals(WeatherAgent(), executor, cases)

    assert [result.passed for result in results] == [False, True]
