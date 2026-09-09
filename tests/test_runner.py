"""Tests for `runa._runner`: the in-house agent loop that replaces `agents.Runner`."""

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from runa._models import StreamDelta
from runa._runner import RunConfig, Runner, gen_trace_id
from runa._types import ModelResponse, ModelSettings, Usage
from runa.exceptions import (
    InputGuardrailTripwireTriggered,
    MaxTurnsExceeded,
    OutputGuardrailTripwireTriggered,
    ToolInputGuardrailTripwireTriggered,
)
from runa.guardrail import GuardrailFunctionOutput, InputGuardrail, OutputGuardrail
from runa.handoff import Handoff
from runa.tool import tool


def _agent(**overrides: Any) -> Any:
    defaults = dict(
        name="TestAgent",
        instructions="be helpful",
        model=None,
        tools=[],
        handoffs=[],
        input_guardrails=[],
        output_guardrails=[],
        output_type=None,
        model_settings=ModelSettings(),
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _text_response(text: str, usage: Usage | None = None) -> ModelResponse:
    return ModelResponse(
        output=[{"role": "assistant", "content": text, "tool_calls": None}],
        usage=usage or Usage(input_tokens=1, output_tokens=1, total_tokens=2, requests=1),
    )


def _tool_call_response(name: str, arguments: str, call_id: str = "call_1") -> ModelResponse:
    return ModelResponse(
        output=[
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {"name": name, "arguments": arguments},
                    }
                ],
            }
        ],
        usage=Usage(input_tokens=1, output_tokens=1, total_tokens=2, requests=1),
    )


class _ScriptedModel:
    """A `Model` stand-in that returns pre-scripted `ModelResponse`s in order."""

    def __init__(self, responses: list[ModelResponse]) -> None:
        self._responses = list(responses)
        self.calls: list[list[Any]] = []

    async def get_response(
        self, system_instructions, input, model_settings, tools, output_schema, handoffs
    ):  # noqa: ANN001, ARG002
        self.calls.append(list(input))
        return self._responses.pop(0)

    async def stream_response(self, *args: Any, **kwargs: Any):  # noqa: ANN001, ANN002, ANN003
        raise NotImplementedError


class _ScriptedStreamingModel:
    """A `Model` stand-in that yields pre-scripted `StreamDelta`s in order."""

    def __init__(self, deltas: list[StreamDelta]) -> None:
        self._deltas = deltas

    async def get_response(self, *args: Any, **kwargs: Any):  # noqa: ANN001, ANN002, ANN003
        raise NotImplementedError

    async def stream_response(
        self, system_instructions, input, model_settings, tools, output_schema, handoffs
    ):  # noqa: ANN001, ARG002
        for delta in self._deltas:
            yield delta


def _run_config() -> RunConfig:
    return RunConfig(workflow_name="TestAgent")


def test_plain_text_turn_returns_final_output() -> None:
    """A model reply with no tool calls becomes the run's final output directly."""
    agent = _agent(model=_ScriptedModel([_text_response("hello there")]))

    result = asyncio.run(Runner.run(agent, "hi", run_config=_run_config()))

    assert result.final_output == "hello there"
    assert result.interruptions == []
    assert result.context_wrapper.usage.input_tokens == 1


def test_run_sync_matches_run() -> None:
    """`run_sync` is a synchronous wrapper with identical behavior to `run`."""
    agent = _agent(model=_ScriptedModel([_text_response("ok")]))

    result = Runner.run_sync(agent, "hi", run_config=_run_config())

    assert result.final_output == "ok"


def test_tool_call_then_final_text() -> None:
    """A tool call is executed and its result fed back before the model gives a final answer."""

    @tool
    def now() -> str:
        """Return a fixed time."""
        return "2024-01-01"

    agent = _agent(
        tools=[now],
        model=_ScriptedModel(
            [_tool_call_response("now", "{}"), _text_response("it is 2024-01-01")]
        ),
    )

    result = asyncio.run(Runner.run(agent, "what time is it?", run_config=_run_config()))

    assert result.final_output == "it is 2024-01-01"
    tool_spans = [s for s in result.trace.spans if s.type == "tool"]
    assert len(tool_spans) == 1
    assert tool_spans[0].name == "now"
    assert tool_spans[0].status == "ok"
    agent_spans = [s for s in result.trace.spans if s.type == "agent"]
    assert agent_spans[0].name == "TestAgent"


def test_tool_error_is_fed_back_and_run_continues() -> None:
    """A tool that raises doesn't abort the run; its span records the error, the run completes."""

    @tool
    def boom() -> str:
        """Raise unconditionally."""
        raise ValueError("boom")

    agent = _agent(
        tools=[boom],
        model=_ScriptedModel([_tool_call_response("boom", "{}"), _text_response("handled it")]),
    )

    result = asyncio.run(Runner.run(agent, "go", run_config=_run_config()))

    assert result.final_output == "handled it"
    (tool_span,) = [s for s in result.trace.spans if s.type == "tool"]
    assert tool_span.status == "error"
    assert "boom" in (tool_span.error or "")


def test_handoff_switches_current_agent() -> None:
    """Calling a handoff's tool switches to the target agent for the rest of the run."""
    target = _agent(name="Target", model=_ScriptedModel([_text_response("handled by target")]))
    handoff = Handoff.from_agent(target)
    main = _agent(
        name="Main",
        handoffs=[handoff],
        model=_ScriptedModel([_tool_call_response(handoff.tool_name, "{}")]),
    )

    result = asyncio.run(Runner.run(main, "please transfer", run_config=_run_config()))

    assert result.final_output == "handled by target"
    handoff_spans = [s for s in result.trace.spans if s.type == "handoff"]
    assert len(handoff_spans) == 1


def test_input_guardrail_tripwire_halts_the_run() -> None:
    """A tripped input guardrail raises before the model is ever called."""

    async def _trip(ctx: Any, agent: Any, value: Any) -> GuardrailFunctionOutput:
        return GuardrailFunctionOutput(output_info="blocked", tripwire_triggered=True)

    agent = _agent(
        input_guardrails=[InputGuardrail(guardrail_function=_trip, name="block_all")],
        model=_ScriptedModel([_text_response("should not be reached")]),
    )

    with pytest.raises(InputGuardrailTripwireTriggered):
        asyncio.run(Runner.run(agent, "hi", run_config=_run_config()))


def test_output_guardrail_tripwire_halts_the_run() -> None:
    """A tripped output guardrail raises after the model responds, before returning."""

    async def _trip(ctx: Any, agent: Any, value: Any) -> GuardrailFunctionOutput:
        return GuardrailFunctionOutput(output_info="too long", tripwire_triggered=len(value) > 3)

    agent = _agent(
        output_guardrails=[OutputGuardrail(guardrail_function=_trip, name="block_long")],
        model=_ScriptedModel([_text_response("way too long")]),
    )

    with pytest.raises(OutputGuardrailTripwireTriggered):
        asyncio.run(Runner.run(agent, "hi", run_config=_run_config()))


def test_tool_input_guardrail_tripwire_halts_the_run() -> None:
    """A tripped tool input guardrail raises and aborts the run, unlike a plain tool exception."""
    from runa.guardrail import guardrail

    @guardrail
    def block_args(args: dict[str, Any]) -> bool:
        """Trip on any arguments."""
        return bool(args)

    @tool(guardrails=[block_args.input])
    def search(query: str) -> str:
        """Search for something."""
        return "results"

    agent = _agent(
        tools=[search],
        model=_ScriptedModel([_tool_call_response("search", '{"query": "x"}')]),
    )

    with pytest.raises(ToolInputGuardrailTripwireTriggered):
        asyncio.run(Runner.run(agent, "search for x", run_config=_run_config()))


def test_max_turns_exceeded() -> None:
    """A model that keeps calling tools forever eventually raises `MaxTurnsExceeded`."""

    @tool
    def loop_tool() -> str:
        """Always return the same thing."""
        return "again"

    responses = [_tool_call_response("loop_tool", "{}") for _ in range(5)]
    agent = _agent(tools=[loop_tool], model=_ScriptedModel(responses))

    with pytest.raises(MaxTurnsExceeded):
        asyncio.run(Runner.run(agent, "go", run_config=RunConfig(workflow_name="x", max_turns=3)))


def test_needs_approval_pauses_then_resumes_on_approve() -> None:
    """A tool requiring approval pauses the run with an `Interruption`; approving resumes it."""

    @tool(needs_approval=True)
    def dangerous() -> str:
        """Do something that needs a human's OK."""
        return "done"

    agent = _agent(
        tools=[dangerous],
        model=_ScriptedModel([_tool_call_response("dangerous", "{}"), _text_response("all done")]),
    )

    result = asyncio.run(Runner.run(agent, "do it", run_config=_run_config()))

    assert result.final_output is None
    assert len(result.interruptions) == 1
    interruption = result.interruptions[0]
    assert interruption.name == "dangerous"

    state = result.to_state()
    state.approve(interruption)
    resumed = asyncio.run(Runner.run(agent, state, run_config=_run_config()))

    assert resumed.final_output == "all done"


def test_needs_approval_rejected_feeds_back_and_continues() -> None:
    """Rejecting a paused tool call resumes with a rejection message, not the tool's result."""

    @tool(needs_approval=True)
    def dangerous() -> str:
        """Do something that needs a human's OK."""
        return "should not run"

    agent = _agent(
        tools=[dangerous],
        model=_ScriptedModel(
            [_tool_call_response("dangerous", "{}"), _text_response("okay, skipped it")]
        ),
    )

    result = asyncio.run(Runner.run(agent, "do it", run_config=_run_config()))
    state = result.to_state()
    state.reject(result.interruptions[0])
    resumed = asyncio.run(Runner.run(agent, state, run_config=_run_config()))

    assert resumed.final_output == "okay, skipped it"


def test_stream_response_yields_text_and_final_message() -> None:
    """Streaming a plain-text reply yields raw deltas, then a `message_output_created` item."""
    from runa._runner import RawResponsesStreamEvent, RunItemStreamEvent

    agent = _agent(
        model=_ScriptedStreamingModel([StreamDelta(text="Hi"), StreamDelta(text=" there")])
    )

    async def collect() -> list[Any]:
        return [event async for event in Runner.run_streamed(agent, "hi", run_config=_run_config())]

    events = asyncio.run(collect())

    raw = [e for e in events if isinstance(e, RawResponsesStreamEvent)]
    assert [d.data.text for d in raw] == ["Hi", " there"]
    (final,) = [
        e
        for e in events
        if isinstance(e, RunItemStreamEvent) and e.name == "message_output_created"
    ]
    assert final.item["content"] == "Hi there"


def test_gen_trace_id_returns_a_fresh_id_each_time() -> None:
    """Two calls to `gen_trace_id` never collide."""
    assert gen_trace_id() != gen_trace_id()


def test_to_input_list_does_not_duplicate_generated_items() -> None:
    """`original_input` must stay independent of `items`, or the turn's own output doubles up.

    `_run_turns` appends every generated message straight onto the `items` list it's handed; if
    `original_input` aliased that same list (as it used to), `to_input_list` would return the
    turn's output twice -- once folded into `original_input`, once from `_generated_items`.
    """
    agent = _agent(model=_ScriptedModel([_text_response("hi there")]))

    result = asyncio.run(
        Runner.run(agent, [{"role": "user", "content": "hi"}], run_config=_run_config())
    )

    assert result.to_input_list() == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hi there", "tool_calls": None},
    ]


def _huge_usage() -> Usage:
    return Usage(input_tokens=200_001, output_tokens=1, total_tokens=200_002, requests=1)


def test_compact_drops_history_before_the_latest_user_message_once_over_budget() -> None:
    """`agent.compact=True` trims older turns once this run's usage crosses 200k tokens."""
    agent = _agent(model=_ScriptedModel([_text_response("ok", usage=_huge_usage())]), compact=True)
    history = [
        {"role": "user", "content": "old question"},
        {"role": "assistant", "content": "old answer", "tool_calls": None},
        {"role": "user", "content": "new question"},
    ]

    result = asyncio.run(Runner.run(agent, history, run_config=_run_config()))

    assert result.to_input_list() == [
        {"role": "user", "content": "new question"},
        {"role": "assistant", "content": "ok", "tool_calls": None},
    ]
    compact_spans = [s for s in result.trace.spans if s.type == "custom" and s.name == "compact"]
    assert compact_spans
    assert all(s.output == {"dropped": 2} for s in compact_spans)


def test_compact_defaults_to_off() -> None:
    """Without `compact=True`, history is left alone no matter how large usage gets."""
    agent = _agent(model=_ScriptedModel([_text_response("ok", usage=_huge_usage())]))
    history = [
        {"role": "user", "content": "old question"},
        {"role": "assistant", "content": "old answer", "tool_calls": None},
        {"role": "user", "content": "new question"},
    ]

    result = asyncio.run(Runner.run(agent, history, run_config=_run_config()))

    assert result.to_input_list() == [
        *history,
        {"role": "assistant", "content": "ok", "tool_calls": None},
    ]
    assert not [s for s in result.trace.spans if s.type == "custom" and s.name == "compact"]


def test_compact_shrinks_session_backed_history_too(tmp_path: Any) -> None:
    """`compact=True` replaces a session's stored history too, not just `agent.history`."""
    from runa.session import SQLiteSession

    session = SQLiteSession("s1", db_path=tmp_path / "runa.db")
    asyncio.run(
        session.add_items(
            [
                {"role": "user", "content": "old question"},
                {"role": "assistant", "content": "old answer", "tool_calls": None},
            ]
        )
    )
    agent = _agent(model=_ScriptedModel([_text_response("ok", usage=_huge_usage())]), compact=True)

    asyncio.run(Runner.run(agent, "new question", session=session, run_config=_run_config()))

    assert asyncio.run(session.get_items()) == [
        {"role": "user", "content": "new question"},
        {"role": "assistant", "content": "ok", "tool_calls": None},
    ]


def test_compact_accepts_a_custom_compactor_callable() -> None:
    """`compact=` also accepts a plain `(items, tokens) -> items|None` callable, not just `True`.

    Its own arbitrary strategy (here: drop the oldest single item, ignoring `usage_tokens`
    entirely) takes effect -- proof the built-in `default_compactor` isn't secretly still in
    charge.
    """
    calls: list[int] = []

    def drop_oldest_item(items: list[Any], usage_tokens: int) -> list[Any] | None:
        calls.append(usage_tokens)
        return items[1:] if len(items) > 1 else None

    agent = _agent(model=_ScriptedModel([_text_response("ok")]), compact=drop_oldest_item)
    history = [
        {"role": "user", "content": "old question"},
        {"role": "assistant", "content": "old answer", "tool_calls": None},
        {"role": "user", "content": "new question"},
    ]

    result = asyncio.run(Runner.run(agent, history, run_config=_run_config()))

    assert calls == [2, 2]  # consulted twice: mid-run on `items`, again on `original_input`
    assert result.to_input_list() == [
        {"role": "assistant", "content": "old answer", "tool_calls": None},
        {"role": "user", "content": "new question"},
        {"role": "assistant", "content": "ok", "tool_calls": None},
    ]


class _MemoryMatchStub:
    """Just enough of `MemoryMatch` for `_memory_block` to format it -- no `runa.memory` import."""

    def __init__(self, text: str) -> None:
        self.text = text


class _FakeMemory:
    """A duck-typed `agent.memory` stand-in: records what the runner calls it with."""

    def __init__(self, matches: list[Any] | None = None) -> None:
        self.matches = matches or []
        self.search_calls: list[tuple[str, str | None]] = []
        self.remembered: list[tuple[str, str | None, Any]] = []

    async def search(self, query: str, *, user_id: str | None = None, k: int = 5) -> list[Any]:
        self.search_calls.append((query, user_id))
        return self.matches

    async def remember_from_conversation(
        self, conversation: str, *, user_id: str | None, model: Any
    ) -> list[str]:
        self.remembered.append((conversation, user_id, model))
        return []


def test_memory_is_searched_before_the_turn_and_injected_as_a_labeled_block() -> None:
    """`agent.memory.search` runs with the user's message, and its matches reach the model."""
    memory = _FakeMemory(matches=[_MemoryMatchStub("User prefers Japanese.")])
    model = _ScriptedModel([_text_response("ok")])
    agent = _agent(model=model, memory=memory)

    result = asyncio.run(Runner.run(agent, "hi", run_config=_run_config()))

    assert memory.search_calls == [("hi", None)]
    sent = [(item.get("role"), item.get("content")) for item in model.calls[0]]
    assert ("system", "Relevant memories:\n- User prefers Japanese.") in sent
    assert result.final_output == "ok"

    (agent_span,) = [s for s in result.trace.spans if s.type == "agent"]
    (retrieval_span,) = [s for s in result.trace.spans if s.type == "retrieval"]
    assert retrieval_span.name == "memory"
    assert retrieval_span.parent_id == agent_span.id
    assert retrieval_span.status == "ok"
    assert retrieval_span.output == {"count": 1}


def test_memory_with_no_matches_injects_nothing() -> None:
    """An empty `search` result leaves the model's input exactly as it would be without memory."""
    memory = _FakeMemory(matches=[])
    model = _ScriptedModel([_text_response("ok")])
    agent = _agent(model=model, memory=memory)

    asyncio.run(Runner.run(agent, "hi", run_config=_run_config()))

    assert model.calls[0] == [{"role": "user", "content": "hi"}]


def test_memory_extraction_runs_after_the_turn_with_the_exchange_and_resolved_model() -> None:
    """After a run, the runner hands memory the turn's exchange and the agent's own model."""
    memory = _FakeMemory()
    model = _ScriptedModel([_text_response("sure, noted")])
    agent = _agent(model=model, memory=memory)

    result = asyncio.run(Runner.run(agent, "I prefer Japanese", run_config=_run_config()))

    assert len(memory.remembered) == 1
    conversation, user_id, resolved_model = memory.remembered[0]
    assert "I prefer Japanese" in conversation
    assert "sure, noted" in conversation
    assert user_id is None
    assert resolved_model is model

    (extraction_span,) = [s for s in result.trace.spans if s.type == "custom"]
    assert extraction_span.name == "memory"
    assert extraction_span.status == "ok"
    assert extraction_span.output == {"stored": 0}


def test_memory_user_id_is_derived_from_the_session(tmp_path: Any) -> None:
    """`Session(user_id=...)` scopes both the retrieval and the extraction call."""
    from runa.session import SQLiteSession

    memory = _FakeMemory()
    session = SQLiteSession("s1", db_path=tmp_path / "runa.db", user_id="u1")
    agent = _agent(model=_ScriptedModel([_text_response("ok")]), memory=memory)

    asyncio.run(Runner.run(agent, "hi", session=session, run_config=_run_config()))

    assert memory.search_calls == [("hi", "u1")]
    assert memory.remembered[0][1] == "u1"


def test_memory_retrieval_failure_degrades_gracefully() -> None:
    """A broken `memory.search` doesn't fail the run; the turn proceeds without memory."""

    class _BoomMemory:
        async def search(self, query: str, *, user_id: str | None = None, k: int = 5) -> list[Any]:
            raise RuntimeError("boom")

    agent = _agent(model=_ScriptedModel([_text_response("ok")]), memory=_BoomMemory())

    result = asyncio.run(Runner.run(agent, "hi", run_config=_run_config()))

    assert result.final_output == "ok"

    (retrieval_span,) = [s for s in result.trace.spans if s.type == "retrieval"]
    assert retrieval_span.status == "error"
    assert retrieval_span.error == "boom"


def test_memory_extraction_failure_degrades_gracefully() -> None:
    """A broken extraction step doesn't fail the run; the final output is unaffected."""

    class _BoomMemory:
        async def search(self, query: str, *, user_id: str | None = None, k: int = 5) -> list[Any]:
            return []

        async def remember_from_conversation(self, *args: Any, **kwargs: Any) -> list[str]:
            raise RuntimeError("boom")

    agent = _agent(model=_ScriptedModel([_text_response("ok")]), memory=_BoomMemory())

    result = asyncio.run(Runner.run(agent, "hi", run_config=_run_config()))

    assert result.final_output == "ok"

    (extraction_span,) = [s for s in result.trace.spans if s.type == "custom"]
    assert extraction_span.status == "error"
    assert extraction_span.error == "boom"


class _KnowledgeMatchStub:
    """Just enough of `KnowledgeMatch` for `_knowledge_block` to format -- no `runa.knowledge`."""

    def __init__(self, text: str) -> None:
        self.text = text


class _FakeKnowledge:
    """A duck-typed `agent.knowledge` stand-in: records what the runner calls it with."""

    def __init__(self, matches: list[Any] | None = None) -> None:
        self.matches = matches or []
        self.search_calls: list[str] = []

    async def search(self, query: str, *, k: int = 5) -> list[Any]:
        self.search_calls.append(query)
        return self.matches


def test_knowledge_is_searched_before_the_turn_and_injected_as_a_labeled_block() -> None:
    """`agent.knowledge.search` runs with the user's message, and its matches reach the model."""
    knowledge = _FakeKnowledge(matches=[_KnowledgeMatchStub("Refunds take 5 business days.")])
    model = _ScriptedModel([_text_response("ok")])
    agent = _agent(model=model, knowledge=knowledge)

    result = asyncio.run(Runner.run(agent, "hi", run_config=_run_config()))

    assert knowledge.search_calls == ["hi"]
    sent = [(item.get("role"), item.get("content")) for item in model.calls[0]]
    assert ("system", "Relevant knowledge:\n- Refunds take 5 business days.") in sent
    assert result.final_output == "ok"

    (retrieval_span,) = [s for s in result.trace.spans if s.type == "retrieval"]
    assert retrieval_span.name == "knowledge"
    assert retrieval_span.status == "ok"
    assert retrieval_span.output == {"count": 1}


def test_knowledge_with_no_matches_injects_nothing() -> None:
    """An empty `search` result leaves the model's input exactly as it would be without it."""
    knowledge = _FakeKnowledge(matches=[])
    model = _ScriptedModel([_text_response("ok")])
    agent = _agent(model=model, knowledge=knowledge)

    asyncio.run(Runner.run(agent, "hi", run_config=_run_config()))

    assert model.calls[0] == [{"role": "user", "content": "hi"}]


def test_knowledge_and_memory_can_both_inject_blocks_before_the_final_message() -> None:
    """Memory and knowledge blocks are both injected, in order, right before the user's message."""
    memory = _FakeMemory(matches=[_MemoryMatchStub("User prefers Japanese.")])
    knowledge = _FakeKnowledge(matches=[_KnowledgeMatchStub("Refunds take 5 business days.")])
    model = _ScriptedModel([_text_response("ok")])
    agent = _agent(model=model, memory=memory, knowledge=knowledge)

    asyncio.run(Runner.run(agent, "hi", run_config=_run_config()))

    contents = [item.get("content") for item in model.calls[0]]
    assert contents == [
        "Relevant memories:\n- User prefers Japanese.",
        "Relevant knowledge:\n- Refunds take 5 business days.",
        "hi",
    ]


def test_knowledge_retrieval_failure_degrades_gracefully() -> None:
    """A broken `knowledge.search` doesn't fail the run; the turn proceeds without knowledge."""

    class _BoomKnowledge:
        async def search(self, query: str, *, k: int = 5) -> list[Any]:
            raise RuntimeError("boom")

    agent = _agent(model=_ScriptedModel([_text_response("ok")]), knowledge=_BoomKnowledge())

    result = asyncio.run(Runner.run(agent, "hi", run_config=_run_config()))

    assert result.final_output == "ok"


def test_agent_without_knowledge_behaves_exactly_as_before() -> None:
    """An agent with no `knowledge` attribute at all runs unaffected -- no lookup, no injection."""
    agent = _agent(model=_ScriptedModel([_text_response("ok")]))
    assert not hasattr(agent, "knowledge")

    result = asyncio.run(Runner.run(agent, "hi", run_config=_run_config()))

    assert result.final_output == "ok"


def test_agent_without_memory_behaves_exactly_as_before() -> None:
    """An agent with no `memory` attribute at all runs unaffected -- no lookup, no injection."""
    agent = _agent(model=_ScriptedModel([_text_response("ok")]))
    assert not hasattr(agent, "memory")

    result = asyncio.run(Runner.run(agent, "hi", run_config=_run_config()))

    assert result.final_output == "ok"


def test_mcp_server_tools_are_merged_in_and_callable() -> None:
    """A tool listed by an `mcp_servers` entry is callable exactly like a `@tool` function."""
    from runa.tool import FunctionTool

    async def on_invoke_tool(ctx: Any, arguments_json: str, call_id: str) -> Any:
        return "42"

    mcp_tool = FunctionTool(
        name="answer",
        description="The answer.",
        params_json_schema={},
        on_invoke_tool=on_invoke_tool,
    )

    class _FakeMCPServer:
        async def list_tools(self) -> list[FunctionTool]:
            return [mcp_tool]

    agent = _agent(
        mcp_servers=[_FakeMCPServer()],
        model=_ScriptedModel([_tool_call_response("answer", "{}"), _text_response("it's 42")]),
    )

    result = asyncio.run(Runner.run(agent, "what's the answer?", run_config=_run_config()))

    assert result.final_output == "it's 42"
    (tool_span,) = [s for s in result.trace.spans if s.type == "tool"]
    assert tool_span.name == "answer"
