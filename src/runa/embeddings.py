"""embeddings.py: text -> vector, for `runa.memory`.

Only OpenAI is wired up: it's the one provider among Runa's chat backends (`_models/_provider.py`)
that also exposes an embeddings endpoint, and `OPENAI_API_KEY` is already the convention every
scaffolded project has (see `cli/new.py`'s `.env` template). Talks to it directly over `httpx2`,
same as `OpenAICompatibleModel`, rather than pulling in the `openai` SDK for one endpoint.
"""

from __future__ import annotations

import os

import httpx2 as httpx

from runa.exceptions import ModelBehaviorError, UserError

DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"

_BASE_URL = "https://api.openai.com/v1/"
_EMBEDDINGS_PATH = "embeddings"

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        api_key = os.environ.get("OPENAI_API_KEY")
        if api_key is None:
            raise UserError("OPENAI_API_KEY is not set. Set it to use runa.memory/embeddings.")
        _client = httpx.AsyncClient(
            base_url=_BASE_URL, headers={"Authorization": f"Bearer {api_key}"}, timeout=60.0
        )
    return _client


async def embed(texts: list[str], *, model: str = DEFAULT_EMBEDDING_MODEL) -> list[list[float]]:
    """Embed `texts` with `model`, returning one vector per input, in the same order."""
    response = await _get_client().post(_EMBEDDINGS_PATH, json={"model": model, "input": texts})
    if response.status_code >= 400:
        raise ModelBehaviorError(
            f"embeddings request failed with {response.status_code}: {response.text[:2000]}"
        )
    data = response.json()["data"]
    return [item["embedding"] for item in sorted(data, key=lambda item: item["index"])]


__all__ = ["DEFAULT_EMBEDDING_MODEL", "embed"]
