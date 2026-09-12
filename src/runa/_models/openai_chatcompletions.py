"""openai_chatcompletions.py: the chat-completions-shaped backend.

Covers OpenAI, Gemini, Llama, DeepSeek, and Qwen, every provider that speaks this wire format.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from typing import Any, cast

import httpx2 as httpx

from runa._models.interface import StreamDelta, _handoff_dict, _tool_dict
from runa._types import (
    InputTokensDetails,
    ModelResponse,
    ModelSettings,
    OutputTokensDetails,
    ToolChoice,
    TResponseInputItem,
    Usage,
)
from runa.exceptions import ModelBehaviorError

_CHAT_COMPLETIONS_PATH = "chat/completions"


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


__all__ = ["OpenAICompatibleModel"]
