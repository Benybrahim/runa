from runa.agent import Agent
from runa.core import Message, Role, Run, ToolCall
from runa.eval import EvalCase, ExpectationFailed, expect, run_evals
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
    else:
        raise AssertionError("expected ExpectationFailed")


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
    assert "goodbye" in results[1].error


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
