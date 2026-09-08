"""Tests for `runa._models`: the six-provider router that replaces litellm."""

import asyncio
from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any

import pytest
from agents import OpenAIChatCompletionsModel
from agents.exceptions import UserError
from openai.types.chat import ChatCompletionMessageFunctionToolCall

from runa._models import (
    AnthropicModel,
    ModelProvider,
    _check_plain_text_output,
    _chunks_from_anthropic_stream,
    _to_anthropic_messages,
    _to_anthropic_tool,
    _to_anthropic_tool_choice,
    _to_chat_completion_message,
    _to_usage,
)


@pytest.fixture(autouse=True)
def _clear_provider_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every provider key starts unset; individual tests set only what they need."""
    for env in (
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "LLAMA_API_KEY",
        "DEEPSEEK_API_KEY",
        "DASHSCOPE_API_KEY",
    ):
        monkeypatch.delenv(env, raising=False)


def test_routes_gpt_to_openai_directly(monkeypatch: pytest.MonkeyPatch) -> None:
    """A `gpt-*` model gets the SDK's own OpenAIChatCompletionsModel, no base_url override."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    model = ModelProvider().get_model("gpt-5.4-nano")

    assert isinstance(model, OpenAIChatCompletionsModel)
    assert str(model._client.base_url) == "https://api.openai.com/v1/"


def test_unrecognized_name_defaults_to_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    """A model name with none of the six prefixes still resolves through OpenAI, like before."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    model = ModelProvider().get_model("o3-mini")

    assert isinstance(model, OpenAIChatCompletionsModel)


@pytest.mark.parametrize(
    ("model_name", "env", "base_url"),
    [
        (
            "gemini-2.5-pro",
            "GEMINI_API_KEY",
            "https://generativelanguage.googleapis.com/v1beta/openai/",
        ),
        ("llama-3.1-70b", "LLAMA_API_KEY", "https://api.llama.com/compat/v1/"),
        ("deepseek-chat", "DEEPSEEK_API_KEY", "https://api.deepseek.com/v1/"),
        (
            "qwen-max",
            "DASHSCOPE_API_KEY",
            "https://dashscope-intl.aliyuncs.com/compatible-mode/v1/",
        ),
    ],
)
def test_routes_each_openai_compatible_provider(
    monkeypatch: pytest.MonkeyPatch, model_name: str, env: str, base_url: str
) -> None:
    """Gemini/Llama/DeepSeek/Qwen each get an OpenAIChatCompletionsModel at their own base_url."""
    monkeypatch.setenv(env, "key")
    model = ModelProvider().get_model(model_name)

    assert isinstance(model, OpenAIChatCompletionsModel)
    assert str(model._client.base_url) == base_url


def test_routes_claude_to_the_anthropic_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    """A `claude-*` model gets `AnthropicModel`, not the OpenAI-compatible path."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "key")
    model = ModelProvider().get_model("claude-sonnet-4-6")

    assert isinstance(model, AnthropicModel)


def test_missing_provider_key_raises_a_clear_error() -> None:
    """An unset provider-specific key names itself, not OPENAI_API_KEY, in the error."""
    with pytest.raises(UserError, match="DEEPSEEK_API_KEY"):
        ModelProvider().get_model("deepseek-chat")


def test_reuses_one_client_per_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """Two calls for the same provider share a client instead of opening a new one each time."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "key")
    provider = ModelProvider()

    first = provider.get_model("deepseek-chat")
    second = provider.get_model("deepseek-coder")

    assert isinstance(first, OpenAIChatCompletionsModel)
    assert isinstance(second, OpenAIChatCompletionsModel)
    assert first._client is second._client


def test_split_system_and_merges_consecutive_tool_results() -> None:
    """Two tool replies to one multi-tool-call turn merge into a single Anthropic user message."""
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": "Be terse."},
        {"role": "user", "content": "weather in two cities?"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"id": "call_1", "function": {"name": "weather", "arguments": '{"city": "NYC"}'}},
                {"id": "call_2", "function": {"name": "weather", "arguments": '{"city": "SF"}'}},
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "sunny"},
        {"role": "tool", "tool_call_id": "call_2", "content": "foggy"},
    ]

    system, turns = _to_anthropic_messages(messages)

    assert system == "Be terse."
    assert [t["role"] for t in turns] == ["user", "assistant", "user"]
    tool_results = turns[2]["content"]
    assert [b["tool_use_id"] for b in tool_results] == ["call_1", "call_2"]
    assert [b["content"] for b in tool_results] == ["sunny", "foggy"]


def test_assistant_turn_carries_text_and_tool_use_blocks() -> None:
    """An assistant message with both text and a tool call becomes two Anthropic content blocks."""
    messages = [
        {
            "role": "assistant",
            "content": "Let me check.",
            "tool_calls": [
                {"id": "call_1", "function": {"name": "weather", "arguments": '{"city": "NYC"}'}}
            ],
        }
    ]

    _, turns = _to_anthropic_messages(messages)

    assert turns[0]["content"] == [
        {"type": "text", "text": "Let me check."},
        {"type": "tool_use", "id": "call_1", "name": "weather", "input": {"city": "NYC"}},
    ]


def test_to_anthropic_tool_translates_the_function_schema() -> None:
    """An OpenAI-shaped function-tool dict maps to Anthropic's name/description/input_schema."""
    tool = {
        "type": "function",
        "function": {
            "name": "weather",
            "description": "Get the weather.",
            "parameters": {"type": "object", "properties": {"city": {"type": "string"}}},
        },
    }

    assert _to_anthropic_tool(tool) == {
        "name": "weather",
        "description": "Get the weather.",
        "input_schema": {"type": "object", "properties": {"city": {"type": "string"}}},
    }


@pytest.mark.parametrize(
    ("converted", "expected"),
    [
        ("auto", {"type": "auto"}),
        ("required", {"type": "any"}),
        ("none", {"type": "none"}),
        (
            {"type": "function", "function": {"name": "weather"}},
            {"type": "tool", "name": "weather"},
        ),
        (None, None),
    ],
)
def test_to_anthropic_tool_choice(converted: Any, expected: dict[str, Any] | None) -> None:
    """Each chat-completions-shaped tool_choice value maps to Anthropic's own shape."""
    assert _to_anthropic_tool_choice(converted) == expected


def test_to_chat_completion_message_collects_text_and_tool_use() -> None:
    """A Claude response's text and tool_use blocks become message content and tool_calls."""
    message = SimpleNamespace(
        content=[
            SimpleNamespace(type="text", text="Checking the weather."),
            SimpleNamespace(type="tool_use", id="call_1", name="weather", input={"city": "NYC"}),
        ],
        stop_reason="tool_use",
    )

    result = _to_chat_completion_message(message)

    assert result.content == "Checking the weather."
    assert result.tool_calls is not None
    call = result.tool_calls[0]
    assert isinstance(call, ChatCompletionMessageFunctionToolCall)
    assert call.id == "call_1"
    assert call.function.name == "weather"
    assert call.function.arguments == '{"city": "NYC"}'
    assert result.refusal is None


def test_to_chat_completion_message_synthesizes_a_refusal() -> None:
    """A `stop_reason="refusal"` with no content still surfaces as an explicit refusal."""
    message = SimpleNamespace(content=[], stop_reason="refusal")

    result = _to_chat_completion_message(message)

    assert result.refusal is not None


def test_to_usage_converts_anthropic_token_counts() -> None:
    """Anthropic's usage fields map onto the SDK's `Usage`, cache fields included."""
    usage = SimpleNamespace(
        input_tokens=10, output_tokens=5, cache_read_input_tokens=2, cache_creation_input_tokens=1
    )

    result = _to_usage(usage)

    assert result.requests == 1
    assert result.input_tokens == 10
    assert result.output_tokens == 5
    assert result.total_tokens == 15
    assert result.input_tokens_details.cached_tokens == 2


def test_check_plain_text_output_allows_none_and_rejects_a_schema() -> None:
    """A structured output schema on a Claude model raises, since translation isn't implemented."""
    _check_plain_text_output(None)

    schema = SimpleNamespace(is_plain_text=lambda: False)
    with pytest.raises(UserError):
        _check_plain_text_output(schema)


async def _stream(events: list[SimpleNamespace]) -> AsyncIterator[SimpleNamespace]:
    for event in events:
        yield event


def test_chunks_from_anthropic_stream_carries_text_and_tool_call_deltas() -> None:
    """Anthropic's SSE events become the OpenAI-shaped chunk deltas the stream handler reads."""
    events = [
        SimpleNamespace(
            type="message_start", message=SimpleNamespace(usage=SimpleNamespace(input_tokens=7))
        ),
        SimpleNamespace(
            type="content_block_delta", index=0, delta=SimpleNamespace(type="text_delta", text="Hi")
        ),
        SimpleNamespace(
            type="content_block_start",
            index=1,
            content_block=SimpleNamespace(type="tool_use", id="call_1", name="weather"),
        ),
        SimpleNamespace(
            type="content_block_delta",
            index=1,
            delta=SimpleNamespace(type="input_json_delta", partial_json='{"city":'),
        ),
        SimpleNamespace(type="message_delta", usage=SimpleNamespace(output_tokens=4)),
    ]

    async def collect() -> list[Any]:
        return [
            c async for c in _chunks_from_anthropic_stream(_stream(events), "claude-sonnet-4-6")
        ]

    chunks = asyncio.run(collect())

    assert chunks[0].choices[0].delta.content == "Hi"
    tool_call_chunk = chunks[1].choices[0].delta.tool_calls[0]
    assert tool_call_chunk.id == "call_1"
    assert tool_call_chunk.function.name == "weather"
    arg_delta = chunks[2].choices[0].delta.tool_calls[0]
    assert arg_delta.index == tool_call_chunk.index
    assert arg_delta.function.arguments == '{"city":'
    assert chunks[3].usage.prompt_tokens == 7
    assert chunks[3].usage.completion_tokens == 4
