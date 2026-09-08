"""Tests for the handoff / delegate / auto subagent wiring in `Agent`."""

import asyncio
from dataclasses import dataclass
from typing import Any, cast

import pytest
from agents import FunctionTool, RunContextWrapper
from agents.exceptions import MaxTurnsExceeded, RunErrorDetails
from agents.testing.model import ScriptedModel
from agents.usage import Usage
from openai.types.responses import (
    ResponseFunctionToolCall,
    ResponseOutputMessage,
    ResponseOutputText,
)

from runa import Agent
from runa.agent import Subagent
from runa.logging import LoggingRunHooks
from runa.tool import tool


def _handoff_names(agent: Agent) -> list[str]:
    """Names of an agent's handoffs, narrowed away from the raw `Handoff` union member."""
    return [h.name for h in agent.handoffs if isinstance(h, Agent)]


def _tool_names(agent: Agent) -> list[str]:
    """Names of an agent's tools, narrowed away from the raw `Tool` union members."""
    return [t.name for t in agent.tools if isinstance(t, FunctionTool)]


class Researcher(Agent):
    """A subagent used across tests."""

    name = "Researcher"
    instructions = "You research topics."


class Translator(Agent):
    """Another subagent used across tests."""

    name = "Translator"
    instructions = "You translate text."


def test_handoff_adds_only_to_handoffs() -> None:
    """`.handoff` wires the subagent as a handoff, not a tool."""

    class Main(Agent):
        name = "Main"
        instructions = "main"
        subagents = [Researcher.handoff]

    agent = Main()

    assert _handoff_names(agent) == ["Researcher"]
    assert agent.tools == []


def test_delegate_adds_only_to_tools() -> None:
    """`.delegate` wires the subagent as a tool, not a handoff."""

    class Main(Agent):
        name = "Main"
        instructions = "main"
        subagents = [Researcher.delegate]

    agent = Main()

    assert agent.handoffs == []
    assert _tool_names(agent) == [Researcher().as_tool(None, None).name]


def test_delegate_tool_name_and_description_override() -> None:
    """Calling a `.delegate` subagent overrides the generated tool's name/description."""

    class Main(Agent):
        name = "Main"
        instructions = "main"
        subagents = [Researcher.delegate(tool_name="do_research", tool_description="Look into it.")]

    agent = Main()

    (tool,) = agent.tools
    assert isinstance(tool, FunctionTool)
    assert tool.name == "do_research"
    assert tool.description == "Look into it."


def test_bare_subagent_wires_both_handoff_and_delegate() -> None:
    """A subagent listed without `.handoff`/`.delegate` lets the model pick either mode."""

    class Main(Agent):
        name = "Main"
        instructions = "main"
        subagents = [Researcher]

    agent = Main()

    assert _handoff_names(agent) == ["Researcher"]
    assert _tool_names(agent) == [Researcher().as_tool(None, None).name]


def test_mixed_modes_wire_independently() -> None:
    """Handoff and delegate subagents in the same list don't interfere with each other."""

    class Main(Agent):
        name = "Main"
        instructions = "main"
        subagents = [Researcher.handoff, Translator.delegate]

    agent = Main()

    assert _handoff_names(agent) == ["Researcher"]
    assert _tool_names(agent) == [Translator().as_tool(None, None).name]


def test_no_subagents_leaves_handoffs_and_tools_empty() -> None:
    """An agent with no `subagents` attribute wires up cleanly."""

    class Main(Agent):
        name = "Main"
        instructions = "main"

    agent = Main()

    assert agent.handoffs == []
    assert agent.tools == []


def test_dict_subagents_wire_by_key() -> None:
    """A `{"handoff": [...], "delegate": [...], "auto": [...]}` dict wires each bucket."""

    class Helper(Agent):
        name = "Helper"
        instructions = "helper"

    class Main(Agent):
        name = "Main"
        instructions = "main"
        subagents = {
            "handoff": [Researcher],
            "delegate": [Translator],
            "auto": [Helper],
        }

    agent = Main()

    assert sorted(_handoff_names(agent)) == ["Helper", "Researcher"]
    assert sorted(_tool_names(agent)) == sorted(
        [Translator().as_tool(None, None).name, Helper().as_tool(None, None).name]
    )


def test_dict_subagents_delegate_bucket_keeps_tool_overrides() -> None:
    """A `.delegate(...)` override still applies inside the dict format's `delegate` bucket."""

    class Main(Agent):
        name = "Main"
        instructions = "main"
        subagents = {
            "delegate": [
                Researcher.delegate(tool_name="do_research", tool_description="Look into it.")
            ]
        }

    agent = Main()

    (tool,) = agent.tools
    assert isinstance(tool, FunctionTool)
    assert tool.name == "do_research"
    assert tool.description == "Look into it."


def test_subagent_descriptor_returns_fresh_immutable_instance() -> None:
    """Each access to `.handoff`/`.delegate` is a new `Subagent`; overrides don't mutate it."""
    first = Researcher.handoff
    second = Researcher.handoff

    assert first is not second
    assert first == second
    assert isinstance(first, Subagent)

    overridden = first(tool_name="custom", tool_description="d")
    assert overridden.tool_name == "custom"
    assert first.tool_name is None, "overriding a copy must not mutate the original"


def test_class_attributes_seed_init_defaults() -> None:
    """Class attributes like `name`/`instructions`/`model` become constructor defaults."""
    agent = Researcher()

    assert agent.name == "Researcher"
    assert agent.instructions == "You research topics."
    assert agent.model == "gpt-5.4-nano"


def test_explicit_kwarg_overrides_class_attribute() -> None:
    """An explicit constructor kwarg wins over the class attribute default."""
    agent = Researcher(model="gpt-4.1")

    assert agent.model == "gpt-4.1"


def test_history_starts_empty() -> None:
    """A freshly constructed agent has no conversation history yet."""
    agent = Researcher()

    assert agent.history == []


def test_usage_starts_empty() -> None:
    """A freshly constructed agent has no accumulated or last usage yet."""
    agent = Researcher()

    assert agent.usage == Usage()
    assert agent.last_usage == Usage()


@dataclass
class _Ctx:
    """A minimal run context used by the dynamic-instructions tests below."""

    label: str


def _single_arg_instructions(context: _Ctx) -> str:
    return f"context={context.label}"


def _two_arg_instructions(context: RunContextWrapper[_Ctx], agent: Any) -> str:
    return f"{agent.name}:{context.context.label}"


def test_single_arg_instructions_resolves_from_run_context() -> None:
    """A one-parameter `(context) -> str` `instructions` is adapted to the SDK's 2-arg shape."""

    class Dynamic(Agent):
        name = "Dynamic"
        instructions = _single_arg_instructions  # pyright: ignore[reportAssignmentType]

    agent = Dynamic()

    prompt = asyncio.run(agent.get_system_prompt(RunContextWrapper(context=_Ctx(label="hi"))))

    assert prompt == "context=hi"


def test_two_arg_instructions_still_supported() -> None:
    """A native SDK-style `(context, agent) -> str` `instructions` passes through unadapted."""

    class Dynamic(Agent):
        name = "Dynamic"
        instructions = _two_arg_instructions

    agent = Dynamic()

    prompt = asyncio.run(agent.get_system_prompt(RunContextWrapper(context=_Ctx(label="hi"))))

    assert prompt == "Dynamic:hi"


def test_string_instructions_pass_through_unchanged() -> None:
    """Plain string instructions are unaffected by the dynamic-instructions adapter."""
    prompt = asyncio.run(Researcher().get_system_prompt(RunContextWrapper(context=None)))

    assert prompt == "You research topics."


class _FakeResult:
    """A stand-in for `RunResult`, just enough for `Agent.run`/`run_sync` to consume."""

    final_output = "ok"
    context_wrapper = RunContextWrapper(context=None, usage=Usage(input_tokens=1, output_tokens=2))

    def to_input_list(self) -> list[Any]:
        return []


def test_run_sync_defaults_to_logging_run_hooks(monkeypatch: pytest.MonkeyPatch) -> None:
    """`run_sync` passes a `LoggingRunHooks` when none is given."""
    captured: dict[str, Any] = {}

    def fake_run_sync(*args: Any, hooks: Any, **kwargs: Any) -> _FakeResult:
        captured["hooks"] = hooks
        return _FakeResult()

    monkeypatch.setattr("runa.agent.Runner.run_sync", staticmethod(fake_run_sync))

    Researcher().run_sync("hi")

    assert isinstance(captured["hooks"], LoggingRunHooks)


def test_run_sync_explicit_hooks_override_the_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """An explicit `hooks` argument is used instead of the default combined hooks."""
    captured: dict[str, Any] = {}
    custom_hooks = LoggingRunHooks()

    def fake_run_sync(*args: Any, hooks: Any, **kwargs: Any) -> _FakeResult:
        captured["hooks"] = hooks
        return _FakeResult()

    monkeypatch.setattr("runa.agent.Runner.run_sync", staticmethod(fake_run_sync))

    Researcher().run_sync("hi", hooks=custom_hooks)

    assert captured["hooks"] is custom_hooks


def test_run_sync_records_and_accumulates_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    """`run_sync` records the call's usage to `last_usage` and adds it to `usage`."""

    def fake_run_sync(*args: Any, **kwargs: Any) -> _FakeResult:
        return _FakeResult()

    monkeypatch.setattr("runa.agent.Runner.run_sync", staticmethod(fake_run_sync))

    agent = Researcher()
    agent.run_sync("hi")
    agent.run_sync("again")

    expected_call_usage = Usage(input_tokens=1, output_tokens=2)
    assert agent.last_usage == expected_call_usage
    assert agent.usage.input_tokens == 2
    assert agent.usage.output_tokens == 4


def test_run_sync_returns_a_completed_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """`run_sync` returns a `Run` with the final output, status, and this call's usage."""

    def fake_run_sync(*args: Any, **kwargs: Any) -> _FakeResult:
        return _FakeResult()

    monkeypatch.setattr("runa.agent.Runner.run_sync", staticmethod(fake_run_sync))

    run = Researcher().run_sync("hi")

    assert run.output == "ok"
    assert run.status == "completed"
    assert run.error is None
    assert run.usage == Usage(input_tokens=1, output_tokens=2)


def test_run_sync_catches_agents_exception_as_error_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """An `AgentsException` (guardrail tripwire, `MaxTurnsExceeded`, ...) is captured, not raised.

    `self.history` is left unchanged, since the turn never completed.
    """
    exc = MaxTurnsExceeded("too many turns")
    exc.run_data = RunErrorDetails(
        input="hi",
        new_items=[],
        raw_responses=[],
        last_agent=cast(Any, None),
        context_wrapper=RunContextWrapper(
            context=None, usage=Usage(input_tokens=5, output_tokens=6)
        ),
        input_guardrail_results=[],
        output_guardrail_results=[],
    )

    def fake_run_sync(*args: Any, **kwargs: Any) -> _FakeResult:
        raise exc

    monkeypatch.setattr("runa.agent.Runner.run_sync", staticmethod(fake_run_sync))

    agent = Researcher()
    run = agent.run_sync("hi")

    assert run.output is None
    assert run.status == "error"
    assert run.error == "too many turns"
    assert run.usage == Usage(input_tokens=5, output_tokens=6)
    assert agent.last_usage == Usage(input_tokens=5, output_tokens=6)
    assert agent.history == []


def test_run_sync_trace_populated_regardless_of_hooks(monkeypatch: pytest.MonkeyPatch) -> None:
    """`Run.trace` is captured via the SDK's own tracing, independent of a custom `hooks=`."""

    def fake_run_sync(*args: Any, **kwargs: Any) -> _FakeResult:
        return _FakeResult()

    monkeypatch.setattr("runa.agent.Runner.run_sync", staticmethod(fake_run_sync))

    run = Researcher().run_sync("hi", hooks=LoggingRunHooks())

    assert run.trace.name == "Researcher"


def _final_message(text: str) -> ResponseOutputMessage:
    return ResponseOutputMessage(
        id="msg_1",
        role="assistant",
        status="completed",
        type="message",
        content=[ResponseOutputText(text=text, type="output_text", annotations=[])],
    )


def test_run_sync_trace_has_agent_and_tool_spans() -> None:
    """A real run's `Run.trace` has an `"agent"` root span and a `"tool"` span for a called tool."""

    @tool
    def now() -> str:
        """Return a fixed time."""
        return "2024-01-01T00:00:00"

    tool_call = ResponseFunctionToolCall(
        call_id="call_1", name="now", arguments="{}", type="function_call"
    )

    class TimeAgent(Agent):
        name = "TimeAgent"
        instructions = "Answer with the time."
        tools = [now]
        model = ScriptedModel(
            steps=[[tool_call], [_final_message("the time is 2024")]], emit_traces=True
        )

    run = TimeAgent().run_sync("what time is it?")

    assert run.status == "completed"
    types_by_name = {span.name: span.type for span in run.trace.spans}
    assert types_by_name["TimeAgent"] == "agent"
    assert types_by_name["now"] == "tool"
    assert all(span.status == "ok" for span in run.trace.spans)


def test_run_sync_trace_records_a_tool_error_span() -> None:
    """A tool that raises doesn't stop the run, but its span in `Run.trace` records the error.

    The SDK feeds the tool's error back to the model as a `function_call_output` and continues
    the turn loop rather than aborting the run, so a second scripted step supplies that follow-up
    response; what this test cares about is that the failed tool's own span is still recorded
    with `status="error"`.
    """

    @tool
    def boom() -> str:
        """Raise unconditionally."""
        raise ValueError("boom")

    tool_call = ResponseFunctionToolCall(
        call_id="call_1", name="boom", arguments="{}", type="function_call"
    )

    class BoomAgent(Agent):
        name = "BoomAgent"
        instructions = "Call the tool."
        tools = [boom]
        model = ScriptedModel(
            steps=[[tool_call], [_final_message("the tool failed")]], emit_traces=True
        )

    run = BoomAgent().run_sync("go")

    tool_spans = [span for span in run.trace.spans if span.type == "tool"]
    assert len(tool_spans) == 1
    assert tool_spans[0].status == "error"
    assert tool_spans[0].error is not None


class _FakeStreamingResult:
    """A stand-in for `RunResultStreaming`, just enough for `Agent.run_streamed` to consume."""

    def __init__(self, events: list[Any], last_response_id: str | None = None) -> None:
        self._events = events
        self.last_response_id = last_response_id
        self.context_wrapper = RunContextWrapper(
            context=None, usage=Usage(input_tokens=3, output_tokens=4)
        )

    async def stream_events(self) -> Any:
        for event in self._events:
            yield event

    def to_input_list(self) -> list[Any]:
        return [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "ok"}]


def test_run_streamed_yields_events_and_updates_history(monkeypatch: pytest.MonkeyPatch) -> None:
    """`run_streamed` yields every SDK stream event, then appends the turn to history."""
    fake_events = ["event-1", "event-2"]

    def fake_run_streamed(*args: Any, **kwargs: Any) -> _FakeStreamingResult:
        return _FakeStreamingResult(fake_events)

    monkeypatch.setattr("runa.agent.Runner.run_streamed", staticmethod(fake_run_streamed))

    agent = Researcher()

    async def _consume() -> list[Any]:
        return [event async for event in agent.run_streamed("hi")]

    events = asyncio.run(_consume())

    assert events == fake_events
    assert agent.history == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "ok"},
    ]
    assert agent.last_usage == Usage(input_tokens=3, output_tokens=4)
    assert agent.usage == Usage(input_tokens=3, output_tokens=4)


def test_run_streamed_defaults_to_logging_run_hooks(monkeypatch: pytest.MonkeyPatch) -> None:
    """`run_streamed` defaults to a `LoggingRunHooks` when none is given."""
    captured: dict[str, Any] = {}

    def fake_run_streamed(*args: Any, hooks: Any, **kwargs: Any) -> _FakeStreamingResult:
        captured["hooks"] = hooks
        return _FakeStreamingResult([])

    monkeypatch.setattr("runa.agent.Runner.run_streamed", staticmethod(fake_run_streamed))

    async def _consume() -> None:
        async for _ in Researcher().run_streamed("hi"):
            pass

    asyncio.run(_consume())

    assert isinstance(captured["hooks"], LoggingRunHooks)


def test_run_streamed_explicit_hooks_override_the_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """An explicit `hooks` argument is used instead of the default combined hooks."""
    captured: dict[str, Any] = {}
    custom_hooks = LoggingRunHooks()

    def fake_run_streamed(*args: Any, hooks: Any, **kwargs: Any) -> _FakeStreamingResult:
        captured["hooks"] = hooks
        return _FakeStreamingResult([])

    monkeypatch.setattr("runa.agent.Runner.run_streamed", staticmethod(fake_run_streamed))

    async def _consume() -> None:
        async for _ in Researcher().run_streamed("hi", hooks=custom_hooks):
            pass

    asyncio.run(_consume())


class _FakeWebSocketSession:
    """A stand-in for `ResponsesWebSocketSession`, recording each `run_streamed` call it gets."""

    def __init__(self, response_ids: list[str]) -> None:
        self._response_ids = list(response_ids)
        self.calls: list[dict[str, Any]] = []

    def run_streamed(self, agent: Any, message: Any, **kwargs: Any) -> _FakeStreamingResult:
        self.calls.append({"agent": agent, "message": message, **kwargs})
        return _FakeStreamingResult([], last_response_id=self._response_ids.pop(0))


def test_run_streamed_with_session_threads_previous_response_id() -> None:
    """A `session` sends only the new message and chains `previous_response_id` across turns."""
    session = cast("Any", _FakeWebSocketSession(["resp-1", "resp-2"]))
    agent = Researcher()

    async def _consume() -> None:
        async for _ in agent.run_streamed("hi", session=session):
            pass
        async for _ in agent.run_streamed("again", session=session):
            pass

    asyncio.run(_consume())

    first_call, second_call = session.calls
    assert first_call["message"] == "hi"
    assert first_call["previous_response_id"] is None
    assert second_call["message"] == "again"
    assert second_call["previous_response_id"] == "resp-1"
    assert agent._last_response_id == "resp-2"
    assert agent.last_usage == Usage(input_tokens=3, output_tokens=4)
    assert agent.usage.input_tokens == 6
    assert agent.usage.output_tokens == 8


def test_evaluate_delegates_to_evaluate_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    """`Agent.evaluate()` forwards straight to `runa.eval.evaluate.evaluate_agent`."""
    from runa.eval.case import Case

    captured: dict[str, Any] = {}

    async def fake_evaluate_agent(agent: Any, dataset: Any, **kwargs: Any) -> str:
        captured["agent"] = agent
        captured["dataset"] = dataset
        captured["kwargs"] = kwargs
        return "a report"

    monkeypatch.setattr("runa.eval.evaluate.evaluate_agent", fake_evaluate_agent)

    agent = Researcher()
    dataset = [Case(input="hi")]
    report = asyncio.run(agent.evaluate(dataset, judge="gpt-5.4", threshold=0.8))

    assert report == "a report"
    assert captured["agent"] is agent
    assert captured["dataset"] is dataset
    assert captured["kwargs"] == {"judge": "gpt-5.4", "threshold": 0.8, "thresholds": None}
