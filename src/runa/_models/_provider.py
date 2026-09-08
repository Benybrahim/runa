"""_provider.py: `ModelProvider`, routing a model name to one of the two backends by its prefix."""

from __future__ import annotations

import os
from dataclasses import dataclass

import httpx2 as httpx
from anthropic import AsyncAnthropic

from runa._models._anthropic import AnthropicModel
from runa._models._base import Model
from runa._models._openai import OpenAICompatibleModel
from runa.exceptions import UserError

_DEFAULT_MODEL = "gpt-5.4-nano"


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


__all__ = ["ModelProvider"]
