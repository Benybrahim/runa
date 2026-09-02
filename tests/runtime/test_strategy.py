from runa.core import Message, Role, Run, ToolCall
from runa.runtime.strategy import CallModel, CallTool, Complete, DefaultStrategy

strategy = DefaultStrategy()


def test_empty_run_calls_model():
    run = Run(input="hi")
    assert isinstance(strategy.step(run), CallModel)


def test_non_assistant_last_message_calls_model():
    run = Run(input="hi")
    run.add_message(Message(role=Role.USER, content="hi"))
    assert isinstance(strategy.step(run), CallModel)


def test_assistant_with_pending_tool_call_calls_tool():
    run = Run(input="hi")
    call = ToolCall(name="get_weather", arguments={"city": "Tokyo"})
    run.add_message(Message(role=Role.ASSISTANT, tool_calls=[call]))

    action = strategy.step(run)
    assert isinstance(action, CallTool)
    assert action.tool_call is call


def test_assistant_with_completed_tool_call_completes():
    run = Run(input="hi")
    call = ToolCall(name="get_weather", arguments={"city": "Tokyo"}, result="sunny")
    run.add_message(Message(role=Role.ASSISTANT, content="", tool_calls=[call]))

    assert isinstance(strategy.step(run), Complete)


def test_assistant_with_no_tool_calls_completes_with_content():
    run = Run(input="hi")
    run.add_message(Message(role=Role.ASSISTANT, content="the answer"))

    action = strategy.step(run)
    assert isinstance(action, Complete)
    assert action.result == "the answer"


def test_tool_result_message_calls_model_again():
    run = Run(input="hi")
    call = ToolCall(name="get_weather", result="sunny")
    run.add_message(Message(role=Role.ASSISTANT, tool_calls=[call]))
    run.add_message(Message(role=Role.TOOL, content="sunny", tool_call_id=call.id))

    assert isinstance(strategy.step(run), CallModel)
