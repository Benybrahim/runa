"""Provider: the contract between the runtime and a specific model API.

Concrete adapters live in `providers/` and translate between this contract
and a vendor's wire format. The runtime depends only on this protocol, never
on a specific vendor.
"""

from typing import Any, Protocol

from runa.core import Message


class Provider(Protocol):
    def complete(
        self,
        *,
        messages: list[Message],
        tools: list[dict[str, Any]],
        model: str | None,
    ) -> Message: ...
