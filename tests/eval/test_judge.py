import pytest

from runa.core import Message, Role, Run, ToolCall
from runa.eval.judge import Judge, JudgeParseError, _format_transcript, _parse_verdict
from tests.fakes import FakeProvider


def test_parse_verdict_reads_pass_and_reasoning():
    verdict = _parse_verdict("PASS\nThe answer directly addresses the question.")

    assert verdict.passed is True
    assert verdict.reasoning == "The answer directly addresses the question."


def test_parse_verdict_reads_fail():
    verdict = _parse_verdict("FAIL\nThe answer ignores the user's question.")

    assert verdict.passed is False
    assert verdict.reasoning == "The answer ignores the user's question."


def test_parse_verdict_defaults_reasoning_when_missing():
    verdict = _parse_verdict("PASS")

    assert verdict.passed is True
    assert verdict.reasoning == "(no reason given)"


def test_parse_verdict_rejects_unrecognized_first_line():
    with pytest.raises(JudgeParseError):
        _parse_verdict("Sure, this looks fine to me.")


def test_format_transcript_includes_input_and_tool_activity():
    run = Run(input="weather in Tokyo?")
    run.add_message(
        Message(
            role=Role.ASSISTANT,
            tool_calls=[ToolCall(name="GetWeather", arguments={"city": "Tokyo"})],
        )
    )
    run.add_message(Message(role=Role.TOOL, content="Tokyo: sunny", tool_call_id="x"))
    run.add_message(Message(role=Role.ASSISTANT, content="It's sunny in Tokyo."))

    transcript = _format_transcript(run)

    assert "weather in Tokyo?" in transcript
    assert "GetWeather({'city': 'Tokyo'})" in transcript
    assert "Tokyo: sunny" in transcript
    assert "It's sunny in Tokyo." in transcript


def test_judge_grade_sends_rubric_and_transcript_with_no_tools():
    run = Run(input="hello")
    response = Message(role=Role.ASSISTANT, content="PASS\nok")
    provider = FakeProvider(responses=[response])
    judge = Judge(provider)

    verdict = judge.grade(run, "be nice")

    assert verdict.passed is True
    call = provider.calls[0]
    assert call["tools"] == []
    assert "be nice" in call["messages"][0].content
    assert "hello" in call["messages"][0].content


def test_judge_grade_raises_when_provider_replies_without_a_verdict():
    run = Run(input="hello")
    provider = FakeProvider(responses=[Message(role=Role.ASSISTANT, content="maybe?")])
    judge = Judge(provider)

    with pytest.raises(JudgeParseError):
        judge.grade(run, "be nice")
