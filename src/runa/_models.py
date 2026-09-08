"""_models.py: Runa's own model provider — two backends, no `openai-agents`, no `openai` SDK.

`ModelProvider.get_model` maps a model name's prefix to a backend. A name starting with `claude`
goes through `AnthropicModel`, talking to Anthropic's own SDK directly — Anthropic's Messages API
isn't chat-completions-shaped, so it's the one backend that needs real translation. Everything else
(`gpt-*`, `gemini-*`, `llama-*`, `deepseek-*`, `qwen-*`, or an unrecognized/bare name) goes through
`OpenAICompatibleModel`, which speaks the chat-completions wire format that OpenAI, Gemini, Llama,
DeepSeek, and Qwen all share — over plain HTTP via `httpx2`, not the `openai` package.

Conversation items are plain chat-completions-shaped message dicts everywhere in Runa (see
`runa._types.TResponseInputItem`); `AnthropicModel` is the only place that ever converts away from
that shape. Tools/handoffs are read structurally here (`.name`/`.description`/`.params_json_schema`
for a tool, `.tool_name`/`.tool_description` for a handoff) rather than importing their concrete
types, so this module has no dependency on `runa.tool`/`runa.handoff`.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from typing import Any, Protocol, cast

import httpx2 as httpx
from anthropic import AsyncAnthropic

from runa._types import (
    InputTokensDetails,
    ModelResponse,
    ModelSettings,
    OutputTokensDetails,
    ToolChoice,
    TResponseInputItem,
    Usage,
)
from runa.exceptions import ModelBehaviorError, UserError

_DEFAULT_MODEL = "gpt-5.4-nano"
_CHAT_COMPLETIONS_PATH = "chat/completions"


class Model(Protocol):
    """What `_runner.py` needs from a model backend: a non-streaming and a streaming call.

    `tools`/`handoffs` are read structurally (see module docstring); `output_schema` is `None` or
    `str` for plain-text output, or any other type to ask the backend for JSON output.
    """

    async def get_response(
        self,
        system_instructions: str | None,
        input: list[TResponseInputItem],
        model_settings: ModelSettings,
        tools: list[Any],
        output_schema: type | None,
        handoffs: list[Any],
    ) -> ModelResponse:
        """Send one turn to the model and return its full response."""
        ...

    def stream_response(
        self,
        system_instructions: str | None,
        input: list[TResponseInputItem],
        model_settings: ModelSettings,
        tools: list[Any],
        output_schema: type | None,
        handoffs: list[Any],
    ) -> AsyncIterator[StreamDelta]:
        """Send one turn to the model and yield incremental `StreamDelta`s as it responds."""
        ...


@dataclass
class StreamDelta:
    """One incremental fragment of a streamed model response.

    Only the fields relevant to a given fragment are set. `_runner.py` accumulates a stream of
    these into a final message: `text` fragments concatenate; a tool-call fragment is keyed by
    `tool_call_index`, with `id`/`name` set once (when the call starts) and `arguments` arriving
    in pieces to be concatenated; `usage` is set once, on whichever fragment carries it (a
    provider's final chunk, in practice).
    """

    text: str | None = None
    tool_call_index: int | None = None
    tool_call_id: str | None = None
    tool_call_name: str | None = None
    tool_call_arguments: str | None = None
    usage: Usage | None = None


def _tool_dict(tool: Any) -> dict[str, Any]:
    """Convert a Runa `FunctionTool`-shaped object to a chat-completions tool definition."""
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description or "",
            "parameters": tool.params_json_schema or {"type": "object", "properties": {}},
        },
    }


def _handoff_dict(handoff: Any) -> dict[str, Any]:
    """Convert a Runa `Handoff`-shaped object to a chat-completions tool definition.

    A handoff takes no structured input from the model — calling it is itself the signal to
    switch agents — so its schema is always an empty object.
    """
    return {
        "type": "function",
        "function": {
            "name": handoff.tool_name,
            "description": handoff.tool_description or "",
            "parameters": {"type": "object", "properties": {}},
        },
    }


@dataclass(frozen=True)
class _Backend:
    """One chat-completions-shaped provider: where it lives and which env var holds its key."""

    prefix: str
    base_url: str
    api_key_env: str


_OPENAI = _Backend("gpt", "https://api.openai.com/v1/", "OPENAI_API_KEY")
_BACKENDS: tuple[_Backend, ...] = (
    _Backend(
        "gemini", "https://generativelanguage.googleapis.com/v1beta/openai/", "GEMINI_API_KEY"
    ),
    _Backend("llama", "https://api.llama.com/compat/v1/", "LLAMA_API_KEY"),
    _Backend("deepseek", "https://api.deepseek.com/v1/", "DEEPSEEK_API_KEY"),
    _Backend(
        "qwen", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1/", "DASHSCOPE_API_KEY"
    ),
)


class ModelProvider:
    """Routes a model name to one of two backends by its prefix.

    A name starting with `claude` goes through `AnthropicModel`; everything else (`gpt-*`,
    `gemini-*`, `llama-*`, `deepseek-*`, `qwen-*`, or an unrecognized/bare name) goes through
    `OpenAICompatibleModel` against that provider's own chat-completions endpoint.
    """

    def __init__(self) -> None:
        """Start with no clients; each is created lazily, on first use, and then reused."""
        self._http_clients: dict[str, httpx.AsyncClient] = {}
        self._anthropic_client: AsyncAnthropic | None = None

    def get_model(self, model_name: str | None) -> Model:
        """Return the `Model` for `model_name` (or Runa's own default, if `None`)."""
        name = model_name or _DEFAULT_MODEL
        lower = name.lower()

        if lower.startswith("claude"):
            return AnthropicModel(name, self._get_anthropic_client())

        backend = next((b for b in _BACKENDS if lower.startswith(b.prefix)), _OPENAI)
        return OpenAICompatibleModel(name, self._get_http_client(backend))

    def _get_http_client(self, backend: _Backend) -> httpx.AsyncClient:
        client = self._http_clients.get(backend.prefix)
        if client is not None:
            return client
        api_key = os.environ.get(backend.api_key_env)
        if api_key is None:
            raise UserError(
                f"{backend.api_key_env} is not set. Set it to use a {backend.prefix}-* model."
            )
        client = httpx.AsyncClient(
            base_url=backend.base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=600.0,
        )
        self._http_clients[backend.prefix] = client
        return client

    def _get_anthropic_client(self) -> AsyncAnthropic:
        if self._anthropic_client is None:
            self._anthropic_client = AsyncAnthropic()
        return self._anthropic_client


def _openai_tool_choice(tool_choice: ToolChoice) -> Any:
    """Map Runa's `ToolChoice` to the chat-completions `tool_choice` shape.

    `"auto"`/`"required"`/`"none"`/`None` pass straight through; any other string is a specific
    tool name, which the wire format wants wrapped in `{"type": "function", "function": {...}}`.
    """
    if tool_choice is None or tool_choice in ("auto", "required", "none"):
        return tool_choice
    return {"type": "function", "function": {"name": tool_choice}}


def _usage_from_openai(usage: dict[str, Any]) -> Usage:
    """Build a `Usage` from a chat-completions response's `usage` object."""
    prompt_details = usage.get("prompt_tokens_details") or {}
    completion_details = usage.get("completion_tokens_details") or {}
    return Usage(
        requests=1,
        input_tokens=usage.get("prompt_tokens", 0),
        output_tokens=usage.get("completion_tokens", 0),
        total_tokens=usage.get("total_tokens", 0),
        input_tokens_details=InputTokensDetails(
            cached_tokens=prompt_details.get("cached_tokens", 0)
        ),
        output_tokens_details=OutputTokensDetails(
            reasoning_tokens=completion_details.get("reasoning_tokens", 0)
        ),
    )


def _raise_for_status(status_code: int, body: str) -> None:
    """Raise `ModelBehaviorError` for a failed request; `body` is capped for legibility."""
    if status_code < 400:
        return
    raise ModelBehaviorError(f"model request failed with {status_code}: {body[:2000]}")


def _openai_deltas(chunk: dict[str, Any]) -> Iterator[StreamDelta]:
    """Turn one chat-completions streaming chunk into zero or more `StreamDelta`s."""
    usage = chunk.get("usage")
    if usage:
        yield StreamDelta(usage=_usage_from_openai(usage))
    choices = chunk.get("choices") or []
    if not choices:
        return
    delta = choices[0].get("delta") or {}
    if delta.get("content"):
        yield StreamDelta(text=delta["content"])
    for call in delta.get("tool_calls") or []:
        function = call.get("function") or {}
        yield StreamDelta(
            tool_call_index=call["index"],
            tool_call_id=call.get("id"),
            tool_call_name=function.get("name"),
            tool_call_arguments=function.get("arguments"),
        )


class OpenAICompatibleModel:
    """Talks to any chat-completions-shaped provider directly over HTTP, via `httpx2`."""

    def __init__(self, model: str, client: httpx.AsyncClient) -> None:
        """Store the model name and the shared, provider-scoped HTTP client to call it through."""
        self.model = model
        self._client = client

    def _request(
        self,
        system_instructions: str | None,
        input: list[TResponseInputItem],
        model_settings: ModelSettings,
        tools: list[Any],
        output_schema: type | None,
        handoffs: list[Any],
    ) -> dict[str, Any]:
        messages = list(input)
        if system_instructions:
            messages = [{"role": "system", "content": system_instructions}, *messages]

        request: dict[str, Any] = {"model": self.model, "messages": messages}
        wire_tools = [_tool_dict(t) for t in tools] + [_handoff_dict(h) for h in handoffs]
        if wire_tools:
            request["tools"] = wire_tools
        if model_settings.tool_choice is not None:
            request["tool_choice"] = _openai_tool_choice(model_settings.tool_choice)
        if model_settings.parallel_tool_calls is not None:
            request["parallel_tool_calls"] = model_settings.parallel_tool_calls
        if model_settings.temperature is not None:
            request["temperature"] = model_settings.temperature
        if model_settings.top_p is not None:
            request["top_p"] = model_settings.top_p
        if model_settings.max_tokens is not None:
            request["max_tokens"] = model_settings.max_tokens
        if output_schema is not None and output_schema is not str:
            request["response_format"] = {"type": "json_object"}
        return request

    async def get_response(
        self,
        system_instructions: str | None,
        input: list[TResponseInputItem],
        model_settings: ModelSettings,
        tools: list[Any],
        output_schema: type | None,
        handoffs: list[Any],
    ) -> ModelResponse:
        """Send one turn to the model and return its full response."""
        request = self._request(
            system_instructions, input, model_settings, tools, output_schema, handoffs
        )
        response = await self._client.post(_CHAT_COMPLETIONS_PATH, json=request)
        _raise_for_status(response.status_code, response.text)
        data = response.json()
        choice = data["choices"][0]["message"]
        message: dict[str, Any] = {
            "role": "assistant",
            "content": choice.get("content"),
            "tool_calls": choice.get("tool_calls") or None,
        }
        usage = _usage_from_openai(data.get("usage") or {})
        return ModelResponse(output=[message], usage=usage, response_id=data.get("id"))

    async def stream_response(
        self,
        system_instructions: str | None,
        input: list[TResponseInputItem],
        model_settings: ModelSettings,
        tools: list[Any],
        output_schema: type | None,
        handoffs: list[Any],
    ) -> AsyncIterator[StreamDelta]:
        """Send one turn to the model and yield incremental `StreamDelta`s as it responds."""
        request = {
            **self._request(
                system_instructions, input, model_settings, tools, output_schema, handoffs
            ),
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        async with self._client.stream("POST", _CHAT_COMPLETIONS_PATH, json=request) as response:
            if response.status_code >= 400:
                body = await response.aread()
                _raise_for_status(response.status_code, body.decode("utf-8", errors="replace"))
            async for sse in httpx.EventSource(response):
                if sse.data == "[DONE]":
                    continue
                for delta in _openai_deltas(cast(dict[str, Any], sse.json())):
                    yield delta


def _check_plain_text_output(output_schema: type | None) -> None:
    """Reject structured output: `AnthropicModel` doesn't translate JSON response formats."""
    if output_schema is not None and output_schema is not str:
        raise UserError(
            "AnthropicModel does not support structured output schemas; use a plain-text "
            "output type (the default, or `str`) for Claude models."
        )


def _text_content(content: Any) -> str:
    """Flatten a chat-completions `content` field (string or a list of parts) to plain text."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    return "".join(
        part["text"]
        for part in content
        if isinstance(part, dict) and isinstance(part.get("text"), str)
    )


def _to_anthropic_messages(messages: list[Any]) -> tuple[str | None, list[dict[str, Any]]]:
    """Split chat-completions messages into Anthropic's `system` string and `messages` turns.

    Anthropic requires strict user/assistant alternation, so consecutive same-role turns (most
    commonly several tool results answering one multi-tool-call assistant turn) are merged into
    one message rather than sent back to back.
    """
    system_parts: list[str] = []
    turns: list[dict[str, Any]] = []
    for message in messages:
        role = message.get("role")
        if role in ("system", "developer"):
            text = _text_content(message.get("content"))
            if text:
                system_parts.append(text)
            continue

        anthropic_role, blocks = _to_anthropic_turn(message)
        if not blocks:
            continue
        if turns and turns[-1]["role"] == anthropic_role:
            turns[-1]["content"].extend(blocks)
        else:
            turns.append({"role": anthropic_role, "content": blocks})

    return "\n".join(system_parts) or None, turns


def _to_anthropic_turn(message: Any) -> tuple[str, list[dict[str, Any]]]:
    role = message.get("role")
    if role == "tool":
        return "user", [
            {
                "type": "tool_result",
                "tool_use_id": message["tool_call_id"],
                "content": _text_content(message.get("content")),
            }
        ]
    if role == "assistant":
        blocks: list[dict[str, Any]] = []
        text = _text_content(message.get("content"))
        if text:
            blocks.append({"type": "text", "text": text})
        for call in message.get("tool_calls") or []:
            function = call["function"]
            blocks.append(
                {
                    "type": "tool_use",
                    "id": call["id"],
                    "name": function["name"],
                    "input": json.loads(function["arguments"] or "{}"),
                }
            )
        return "assistant", blocks
    return "user", [{"type": "text", "text": _text_content(message.get("content"))}]


def _to_anthropic_tool(tool: dict[str, Any]) -> dict[str, Any]:
    function = tool["function"]
    return {
        "name": function["name"],
        "description": function.get("description") or "",
        "input_schema": function.get("parameters") or {"type": "object", "properties": {}},
    }


def _to_anthropic_tool_choice(tool_choice: ToolChoice) -> dict[str, Any] | None:
    """Map Runa's `ToolChoice` to Anthropic's `tool_choice` shape."""
    if tool_choice is None:
        return None
    if tool_choice == "auto":
        return {"type": "auto"}
    if tool_choice == "required":
        return {"type": "any"}
    if tool_choice == "none":
        return {"type": "none"}
    return {"type": "tool", "name": tool_choice}


def _to_usage(usage: Any) -> Usage:
    return Usage(
        requests=1,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        total_tokens=usage.input_tokens + usage.output_tokens,
        input_tokens_details=InputTokensDetails(
            cached_tokens=usage.cache_read_input_tokens or 0,
            cache_write_tokens=usage.cache_creation_input_tokens or 0,
        ),
        output_tokens_details=OutputTokensDetails(reasoning_tokens=0),
    )


class AnthropicModel:
    """Talks to Claude directly through the `anthropic` SDK's Messages API."""

    def __init__(self, model: str, client: AsyncAnthropic) -> None:
        """Store the model name and the shared Anthropic client to call it through."""
        self.model = model
        self._client = client

    def _request(
        self,
        system_instructions: str | None,
        input: list[TResponseInputItem],
        model_settings: ModelSettings,
        tools: list[Any],
        handoffs: list[Any],
    ) -> dict[str, Any]:
        messages = list(input)
        if system_instructions:
            messages = [{"role": "system", "content": system_instructions}, *messages]
        system, turns = _to_anthropic_messages(messages)

        wire_tools = [_tool_dict(t) for t in tools] + [_handoff_dict(h) for h in handoffs]

        request: dict[str, Any] = {
            "model": self.model,
            "messages": turns,
            "max_tokens": model_settings.max_tokens or 4096,
        }
        if system:
            request["system"] = system
        if wire_tools:
            request["tools"] = [_to_anthropic_tool(t) for t in wire_tools]
        tool_choice = _to_anthropic_tool_choice(model_settings.tool_choice)
        if tool_choice:
            request["tool_choice"] = tool_choice
        if model_settings.temperature is not None:
            request["temperature"] = model_settings.temperature
        if model_settings.top_p is not None:
            request["top_p"] = model_settings.top_p
        return request

    async def get_response(
        self,
        system_instructions: str | None,
        input: list[TResponseInputItem],
        model_settings: ModelSettings,
        tools: list[Any],
        output_schema: type | None,
        handoffs: list[Any],
    ) -> ModelResponse:
        """Send one turn to the model and return its full response."""
        _check_plain_text_output(output_schema)
        request = self._request(system_instructions, input, model_settings, tools, handoffs)
        response = await self._client.messages.create(**request)

        message: dict[str, Any] = _to_chat_message(response)
        usage = _to_usage(response.usage)
        return ModelResponse(output=[message], usage=usage, response_id=response.id)

    async def stream_response(
        self,
        system_instructions: str | None,
        input: list[TResponseInputItem],
        model_settings: ModelSettings,
        tools: list[Any],
        output_schema: type | None,
        handoffs: list[Any],
    ) -> AsyncIterator[StreamDelta]:
        """Send one turn to the model and yield incremental `StreamDelta`s as it responds."""
        _check_plain_text_output(output_schema)
        request = self._request(system_instructions, input, model_settings, tools, handoffs)
        raw_stream = await self._client.messages.create(stream=True, **request)
        async for delta in _anthropic_deltas(raw_stream):
            yield delta


def _to_chat_message(message: Any) -> dict[str, Any]:
    """Convert an Anthropic `Message` into a chat-completions-shaped assistant message dict."""
    text_parts: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    for block in message.content:
        if block.type == "text":
            text_parts.append(block.text)
        elif block.type == "tool_use":
            tool_calls.append(
                {
                    "id": block.id,
                    "type": "function",
                    "function": {"name": block.name, "arguments": json.dumps(block.input)},
                }
            )
    return {
        "role": "assistant",
        "content": "".join(text_parts) or None,
        "tool_calls": tool_calls or None,
    }


async def _anthropic_deltas(stream: AsyncIterator[Any]) -> AsyncIterator[StreamDelta]:
    """Turn Anthropic's raw SSE events into `StreamDelta`s."""
    input_tokens = 0
    async for event in stream:
        if event.type == "message_start":
            input_tokens = event.message.usage.input_tokens
        elif event.type == "content_block_start" and event.content_block.type == "tool_use":
            block = event.content_block
            yield StreamDelta(
                tool_call_index=event.index,
                tool_call_id=block.id,
                tool_call_name=block.name,
                tool_call_arguments="",
            )
        elif event.type == "content_block_delta":
            delta = event.delta
            if delta.type == "text_delta":
                yield StreamDelta(text=delta.text)
            elif delta.type == "input_json_delta":
                yield StreamDelta(
                    tool_call_index=event.index, tool_call_arguments=delta.partial_json
                )
        elif event.type == "message_delta" and event.usage is not None:
            output_tokens = event.usage.output_tokens or 0
            yield StreamDelta(
                usage=Usage(
                    requests=1,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=input_tokens + output_tokens,
                )
            )


__all__ = ["AnthropicModel", "Model", "ModelProvider", "OpenAICompatibleModel", "StreamDelta"]
