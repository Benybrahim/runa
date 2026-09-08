"""_models.py: Runa's own model provider — six providers, no litellm.

`ModelProvider.get_model` maps a model name's prefix to a backend. `gpt`/unrecognized names go
straight to OpenAI; `gemini`, `llama`, `deepseek`, and `qwen` speak OpenAI's chat-completions wire
format natively, so they're just an `AsyncOpenAI` client pointed at that provider's own endpoint,
reused through the SDK's own `OpenAIChatCompletionsModel`. `claude` is the one exception —
Anthropic's Messages API isn't OpenAI-shaped — so `AnthropicModel` below talks to it directly
through the `anthropic` SDK, translating requests and responses through the same
`Converter`/`ChatCmplStreamHandler` machinery `OpenAIChatCompletionsModel` uses internally, rather
than reimplementing response/event construction from scratch.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, cast

from agents import (
    Model,
    ModelResponse,
    ModelSettings,
    ModelTracing,
    OpenAIChatCompletionsModel,
    Usage,
)
from agents import ModelProvider as BaseModelProvider
from agents.exceptions import UserError
from agents.handoffs import Handoff
from agents.items import TResponseInputItem, TResponseStreamEvent
from agents.models._trace import model_config_for_trace
from agents.models.chatcmpl_converter import Converter
from agents.models.chatcmpl_stream_handler import ChatCmplStreamHandler
from agents.models.default_models import get_default_model
from agents.models.fake_id import FAKE_RESPONSES_ID
from agents.tool import Tool
from agents.tracing import generation_span
from agents.usage import _make_input_tokens_details
from agents.util._error_tracing import model_span_errors
from anthropic import AsyncAnthropic
from openai import AsyncOpenAI, omit
from openai.types.chat import ChatCompletionMessage, ChatCompletionMessageFunctionToolCall
from openai.types.chat.chat_completion_chunk import (
    ChatCompletionChunk,
    Choice,
    ChoiceDelta,
    ChoiceDeltaToolCall,
    ChoiceDeltaToolCallFunction,
)
from openai.types.chat.chat_completion_message_function_tool_call import Function
from openai.types.chat.chat_completion_message_tool_call import ChatCompletionMessageToolCallUnion
from openai.types.completion_usage import CompletionUsage
from openai.types.responses import Response
from openai.types.responses.response_prompt_param import ResponsePromptParam
from openai.types.responses.response_usage import OutputTokensDetails


@dataclass(frozen=True)
class _Backend:
    """One OpenAI-compatible provider: where it lives and which env var holds its key."""

    prefix: str
    base_url: str | None
    api_key_env: str


_OPENAI = _Backend("gpt", None, "OPENAI_API_KEY")
_BACKENDS: tuple[_Backend, ...] = (
    _Backend(
        "gemini", "https://generativelanguage.googleapis.com/v1beta/openai/", "GEMINI_API_KEY"
    ),
    _Backend("llama", "https://api.llama.com/compat/v1", "LLAMA_API_KEY"),
    _Backend("deepseek", "https://api.deepseek.com/v1", "DEEPSEEK_API_KEY"),
    _Backend("qwen", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1", "DASHSCOPE_API_KEY"),
)


class ModelProvider(BaseModelProvider):
    """Routes a model name to one of six providers by its prefix.

    A name starting with `claude` goes through `AnthropicModel`; `gemini`/`llama`/`deepseek`/`qwen`
    go through their own OpenAI-compatible endpoint; anything else (`gpt-*`, `o*`, a bare or
    fine-tuned name) defaults to OpenAI directly, same as an unprefixed name always has.
    """

    def __init__(self) -> None:
        self._openai_clients: dict[str, AsyncOpenAI] = {}
        self._anthropic_client: AsyncAnthropic | None = None

    def get_model(self, model_name: str | None) -> Model:
        name = model_name or get_default_model()
        lower = name.lower()

        if lower.startswith("claude"):
            return AnthropicModel(name, self._get_anthropic_client())

        backend = next((b for b in _BACKENDS if lower.startswith(b.prefix)), _OPENAI)
        return OpenAIChatCompletionsModel(
            model=name, openai_client=self._get_openai_client(backend)
        )

    def _get_openai_client(self, backend: _Backend) -> AsyncOpenAI:
        client = self._openai_clients.get(backend.prefix)
        if client is not None:
            return client
        api_key = os.environ.get(backend.api_key_env)
        if api_key is None and backend.base_url is not None:
            raise UserError(
                f"{backend.api_key_env} is not set. Set it to use a {backend.prefix}-* model."
            )
        client = AsyncOpenAI(api_key=api_key, base_url=backend.base_url)
        self._openai_clients[backend.prefix] = client
        return client

    def _get_anthropic_client(self) -> AsyncAnthropic:
        if self._anthropic_client is None:
            self._anthropic_client = AsyncAnthropic()
        return self._anthropic_client


class AnthropicModel(Model):
    """Talks to Claude directly through the `anthropic` SDK's Messages API."""

    def __init__(self, model: str, client: AsyncAnthropic) -> None:
        self.model = model
        self._client = client

    async def get_response(
        self,
        system_instructions: str | None,
        input: str | list[TResponseInputItem],
        model_settings: ModelSettings,
        tools: list[Tool],
        output_schema: Any | None,
        handoffs: list[Handoff],
        tracing: ModelTracing,
        *,
        previous_response_id: str | None = None,
        conversation_id: str | None = None,
        prompt: ResponsePromptParam | None = None,
    ) -> ModelResponse:
        _check_plain_text_output(output_schema)
        with (
            generation_span(
                model=self.model,
                model_config=model_config_for_trace(
                    model_settings, extra_config={"model_impl": "anthropic"}
                ),
                disabled=tracing.is_disabled(),
            ) as span,
            model_span_errors(
                span,
                message="Error getting response",
                trace_include_sensitive_data=tracing.include_data(),
            ),
        ):
            request = self._request(system_instructions, input, model_settings, tools, handoffs)
            message = await self._client.messages.create(**request)

            chat_message = _to_chat_completion_message(message)
            usage = _to_usage(message.usage)

            if tracing.include_data():
                span.span_data.output = [chat_message.model_dump()]
            span.span_data.usage = {
                "requests": usage.requests,
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "total_tokens": usage.total_tokens,
                "input_tokens_details": usage.input_tokens_details.model_dump(),
                "output_tokens_details": usage.output_tokens_details.model_dump(),
            }

            items = Converter.message_to_output_items(
                chat_message, provider_data={"model": self.model, "response_id": message.id}
            )
            return ModelResponse(output=items, usage=usage, response_id=None)

    async def stream_response(
        self,
        system_instructions: str | None,
        input: str | list[TResponseInputItem],
        model_settings: ModelSettings,
        tools: list[Tool],
        output_schema: Any | None,
        handoffs: list[Handoff],
        tracing: ModelTracing,
        *,
        previous_response_id: str | None = None,
        conversation_id: str | None = None,
        prompt: ResponsePromptParam | None = None,
    ) -> AsyncIterator[TResponseStreamEvent]:
        _check_plain_text_output(output_schema)
        with (
            generation_span(
                model=self.model,
                model_config=model_config_for_trace(
                    model_settings, extra_config={"model_impl": "anthropic"}
                ),
                disabled=tracing.is_disabled(),
            ) as span,
            model_span_errors(
                span,
                message="Error streaming response",
                trace_include_sensitive_data=tracing.include_data(),
            ),
        ):
            request = self._request(system_instructions, input, model_settings, tools, handoffs)
            raw_stream = await self._client.messages.create(stream=True, **request)
            chunks = _chunks_from_anthropic_stream(raw_stream, self.model)

            skeleton = Response(
                id=FAKE_RESPONSES_ID,
                created_at=time.time(),
                model=self.model,
                object="response",
                output=[],
                tool_choice="auto",
                top_p=model_settings.top_p,
                temperature=model_settings.temperature,
                tools=[],
                parallel_tool_calls=bool(request.get("tools")),
                reasoning=model_settings.reasoning,
            )

            final_response: Response | None = None
            async for event in ChatCmplStreamHandler.handle_stream(
                skeleton, cast(Any, chunks), model=self.model
            ):
                if event.type == "response.completed":
                    final_response = event.response
                yield event

            if final_response is not None:
                if tracing.include_data():
                    span.span_data.output = [final_response.model_dump()]
                stream_usage = final_response.usage
                if stream_usage is not None:
                    input_details = stream_usage.input_tokens_details
                    span.span_data.usage = {
                        "requests": 1,
                        "input_tokens": stream_usage.input_tokens,
                        "output_tokens": stream_usage.output_tokens,
                        "total_tokens": stream_usage.total_tokens,
                        "input_tokens_details": input_details.model_dump()
                        if input_details is not None
                        else {"cached_tokens": 0, "cache_write_tokens": 0},
                        "output_tokens_details": {"reasoning_tokens": 0},
                    }

    def _request(
        self,
        system_instructions: str | None,
        input: str | list[TResponseInputItem],
        model_settings: ModelSettings,
        tools: list[Tool],
        handoffs: list[Handoff],
    ) -> dict[str, Any]:
        converted = Converter.items_to_messages(input, model=self.model)
        if system_instructions:
            converted.insert(0, {"role": "system", "content": system_instructions})
        system, messages = _to_anthropic_messages(converted)

        converted_tools = [Converter.tool_to_openai(t) for t in tools]
        converted_tools += [Converter.convert_handoff_tool(h) for h in handoffs]

        request: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": model_settings.max_tokens or 4096,
        }
        if system:
            request["system"] = system
        if converted_tools:
            request["tools"] = [_to_anthropic_tool(t) for t in converted_tools]
        tool_choice = _to_anthropic_tool_choice(
            Converter.convert_tool_choice(model_settings.tool_choice)
        )
        if tool_choice:
            request["tool_choice"] = tool_choice
        if model_settings.temperature is not None:
            request["temperature"] = model_settings.temperature
        if model_settings.top_p is not None:
            request["top_p"] = model_settings.top_p
        return request


def _check_plain_text_output(output_schema: Any | None) -> None:
    """Reject structured output schemas: `AnthropicModel` doesn't translate `response_format`."""
    if output_schema is not None and not output_schema.is_plain_text():
        raise UserError(
            "AnthropicModel does not support structured output schemas; use a plain-text "
            "output type (the default) for Claude models."
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


def _to_anthropic_tool(tool: Any) -> dict[str, Any]:
    function = tool["function"]
    return {
        "name": function["name"],
        "description": function.get("description") or "",
        "input_schema": function.get("parameters") or {"type": "object", "properties": {}},
    }


def _to_anthropic_tool_choice(converted: Any) -> dict[str, Any] | None:
    """Map `Converter.convert_tool_choice`'s chat-completions-shaped result to Anthropic's."""
    if converted is omit or converted is None:
        return None
    if converted == "auto":
        return {"type": "auto"}
    if converted == "required":
        return {"type": "any"}
    if converted == "none":
        return {"type": "none"}
    if isinstance(converted, dict):
        return {"type": "tool", "name": converted["function"]["name"]}
    return None


def _to_chat_completion_message(message: Any) -> ChatCompletionMessage:
    text_parts: list[str] = []
    tool_calls: list[ChatCompletionMessageToolCallUnion] = []
    for block in message.content:
        if block.type == "text":
            text_parts.append(block.text)
        elif block.type == "tool_use":
            tool_calls.append(
                ChatCompletionMessageFunctionToolCall(
                    id=block.id,
                    type="function",
                    function=Function(name=block.name, arguments=json.dumps(block.input)),
                )
            )
    refusal = (
        "Response withheld by the provider's content filter."
        if message.stop_reason == "refusal"
        else None
    )
    return ChatCompletionMessage(
        role="assistant",
        content="".join(text_parts) or None,
        tool_calls=tool_calls or None,
        refusal=refusal,
    )


def _to_usage(usage: Any) -> Usage:
    return Usage(
        requests=1,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        total_tokens=usage.input_tokens + usage.output_tokens,
        input_tokens_details=_make_input_tokens_details(
            cached_tokens=usage.cache_read_input_tokens,
            cache_write_tokens=usage.cache_creation_input_tokens,
        ),
        output_tokens_details=OutputTokensDetails(reasoning_tokens=0),
    )


async def _chunks_from_anthropic_stream(
    stream: AsyncIterator[Any], model: str
) -> AsyncIterator[ChatCompletionChunk]:
    """Turn Anthropic's raw SSE events into `ChatCompletionChunk`s `ChatCmplStreamHandler` expects.

    Only the deltas the handler actually reads are synthesized (text, tool-call id/name/arguments
    fragments, and a trailing usage-only chunk); finish_reason is left unset since the handler
    finalizes a turn when this generator ends, not from any particular chunk.
    """
    chunk_id = FAKE_RESPONSES_ID
    created = int(time.time())
    tool_call_index: dict[int, int] = {}
    input_tokens = 0

    def chunk(delta: ChoiceDelta, usage: CompletionUsage | None = None) -> ChatCompletionChunk:
        return ChatCompletionChunk(
            id=chunk_id,
            choices=[Choice(index=0, delta=delta, finish_reason=None)],
            created=created,
            model=model,
            object="chat.completion.chunk",
            usage=usage,
        )

    async for event in stream:
        if event.type == "message_start":
            input_tokens = event.message.usage.input_tokens
        elif event.type == "content_block_start" and event.content_block.type == "tool_use":
            block = event.content_block
            tool_call_index[event.index] = len(tool_call_index)
            yield chunk(
                ChoiceDelta(
                    tool_calls=[
                        ChoiceDeltaToolCall(
                            index=tool_call_index[event.index],
                            id=block.id,
                            type="function",
                            function=ChoiceDeltaToolCallFunction(name=block.name, arguments=""),
                        )
                    ]
                )
            )
        elif event.type == "content_block_delta":
            delta = event.delta
            if delta.type == "text_delta":
                yield chunk(ChoiceDelta(content=delta.text))
            elif delta.type == "input_json_delta":
                raw_index = event.index
                # Not `.get(raw_index, raw_index)`: pyright can't tell that overload apart from
                # the one-arg form here (both operands come through as `Any`), and infers
                # `int | None`.
                index = tool_call_index[raw_index] if raw_index in tool_call_index else raw_index  # noqa: SIM401
                yield chunk(
                    ChoiceDelta(
                        tool_calls=[
                            ChoiceDeltaToolCall(
                                index=index,
                                function=ChoiceDeltaToolCallFunction(arguments=delta.partial_json),
                            )
                        ]
                    )
                )
        elif event.type == "message_delta" and event.usage is not None:
            output_tokens = event.usage.output_tokens or 0
            yield chunk(
                ChoiceDelta(),
                usage=CompletionUsage(
                    prompt_tokens=input_tokens,
                    completion_tokens=output_tokens,
                    total_tokens=input_tokens + output_tokens,
                ),
            )
