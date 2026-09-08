"""Tests for `runa.tracing.observe`: the privacy/size policy and its `with`/bare-call forms."""

import asyncio
from types import SimpleNamespace
from typing import Any

from runa._runner import RunConfig, Runner
from runa._types import ModelResponse, ModelSettings, Usage
from runa.tool import tool
from runa.tracing import config, observe


class _TextModel:
    def __init__(self, text: str) -> None:
        self._text = text

    async def get_response(self, *args: Any, **kwargs: Any) -> ModelResponse:  # noqa: ANN002, ANN003
        return ModelResponse(
            output=[{"role": "assistant", "content": self._text, "tool_calls": None}],
            usage=Usage(input_tokens=1, output_tokens=1, total_tokens=2, requests=1),
        )


def _tool_call_then_text(name: str, arguments: str, text: str) -> list[ModelResponse]:
    return [
        ModelResponse(
            output=[
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": name, "arguments": arguments},
                        }
                    ],
                }
            ],
            usage=Usage(input_tokens=1, output_tokens=1, total_tokens=2, requests=1),
        ),
        ModelResponse(
            output=[{"role": "assistant", "content": text, "tool_calls": None}],
            usage=Usage(input_tokens=1, output_tokens=1, total_tokens=2, requests=1),
        ),
    ]


class _ScriptedModel:
    def __init__(self, responses: list[ModelResponse]) -> None:
        self._responses = list(responses)

    async def get_response(self, *args: Any, **kwargs: Any) -> ModelResponse:  # noqa: ANN002, ANN003
        return self._responses.pop(0)


def _agent_with_tool() -> Any:
    @tool
    def now(x: int) -> str:
        """Return a fixed time, ignoring `x`."""
        return "ok"

    return SimpleNamespace(
        name="TestAgent",
        instructions="hi",
        model=_ScriptedModel(_tool_call_then_text("now", '{"x": 1}', "done")),
        tools=[now],
        handoffs=[],
        input_guardrails=[],
        output_guardrails=[],
        output_type=None,
        model_settings=ModelSettings(),
    )


def test_observe_bare_call_leaves_the_setting_applied() -> None:
    """A plain `observe(capture_inputs=False)` call (no `with`) applies immediately and sticks."""
    observe(capture_inputs=False)
    try:
        assert config.capture_inputs() is False
    finally:
        observe(capture_inputs=True)


def test_observe_context_manager_restores_the_previous_setting_on_exit() -> None:
    """`with observe(...):` restores whatever policy was active before it, once the block ends."""
    assert config.capture_inputs() is True

    with observe(capture_inputs=False):
        assert config.capture_inputs() is False

    assert config.capture_inputs() is True


def test_capture_inputs_false_means_tool_span_input_is_not_recorded() -> None:
    """`observe(capture_inputs=False)` means a captured tool span's `input` stays `None`."""
    agent = _agent_with_tool()
    with observe(capture_inputs=False):
        result = asyncio.run(Runner.run(agent, "hi", run_config=RunConfig(workflow_name="T")))

    tool_span = next(span for span in result.trace.spans if span.type == "tool")
    assert tool_span.input is None
    assert tool_span.output == "ok"


def test_redact_scrubs_matching_keys_from_dict_shaped_output() -> None:
    """`redact=["email"]` replaces that key's value with `"[REDACTED]"` in dict-shaped output."""

    @tool
    def lookup() -> dict[str, Any]:
        """Return a dict containing an email."""
        return {"email": "a@b.com", "id": 1}

    agent = SimpleNamespace(
        name="TestAgent",
        instructions="hi",
        model=_ScriptedModel(_tool_call_then_text("lookup", "{}", "done")),
        tools=[lookup],
        handoffs=[],
        input_guardrails=[],
        output_guardrails=[],
        output_type=None,
        model_settings=ModelSettings(),
    )

    with observe(redact=["email"]):
        result = asyncio.run(Runner.run(agent, "hi", run_config=RunConfig(workflow_name="T")))

    tool_span = next(span for span in result.trace.spans if span.type == "tool")
    assert tool_span.output["email"] == "[REDACTED]"
    assert tool_span.output["id"] == 1


def test_max_input_bytes_truncates_a_long_tool_argument() -> None:
    """`max_input_bytes` truncates a tool span's input once it exceeds the configured size."""

    @tool
    def now(x: str) -> str:
        """Return a fixed time, ignoring `x`."""
        return "ok"

    long_arg = "x" * 100
    agent = SimpleNamespace(
        name="TestAgent",
        instructions="hi",
        model=_ScriptedModel(_tool_call_then_text("now", f'{{"x": "{long_arg}"}}', "done")),
        tools=[now],
        handoffs=[],
        input_guardrails=[],
        output_guardrails=[],
        output_type=None,
        model_settings=ModelSettings(),
    )

    with observe(max_input_bytes=10):
        result = asyncio.run(Runner.run(agent, "hi", run_config=RunConfig(workflow_name="T")))

    tool_span = next(span for span in result.trace.spans if span.type == "tool")
    assert len(tool_span.input) < 100
    assert tool_span.input.endswith("[truncated]")
