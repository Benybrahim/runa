"""Tests for the `@approval` decorator."""

import asyncio
from typing import Any, cast

import pytest

from runa import approval, tool
from runa._types import RunContextWrapper


def _run(predicate: Any, params: dict[str, Any], call_id: str = "call_1") -> bool:
    """Call a wrapped `needs_approval` callable directly, awaiting its always-async wrapper."""
    ctx = cast(RunContextWrapper[Any], RunContextWrapper(context=None))
    return asyncio.run(predicate(ctx, params, call_id))


def test_approval_binds_params_by_name() -> None:
    """A predicate's parameters are looked up by name from the tool's parsed arguments."""

    @approval
    def requires_review(subject: str) -> bool:
        """Trip for refund-related subjects."""
        return "refund" in subject.lower()

    assert _run(requires_review, {"subject": "Refund request", "body": "..."})
    assert not _run(requires_review, {"subject": "Hello", "body": "..."})


def test_approval_works_on_lambda() -> None:
    """A bare lambda works the same as a `def`."""
    requires_review = approval(lambda subject: "refund" in subject.lower())

    assert _run(requires_review, {"subject": "Refund request"})
    assert not _run(requires_review, {"subject": "Hello"})


def test_approval_exposes_ctx_and_call_id_by_name() -> None:
    """Naming a parameter `ctx`/`call_id` receives the run context/call id, not a tool arg."""
    seen: dict[str, Any] = {}

    @approval
    def requires_review(ctx: RunContextWrapper[Any], call_id: str, subject: str) -> bool:
        seen["ctx"] = ctx
        seen["call_id"] = call_id
        return bool(subject)

    assert _run(requires_review, {"subject": "x"}, call_id="call_42")
    assert seen["call_id"] == "call_42"
    assert isinstance(seen["ctx"], RunContextWrapper)


def test_approval_supports_async_predicates() -> None:
    """An `async def` predicate is awaited before its result is used."""

    @approval
    async def requires_review(subject: str) -> bool:
        return "refund" in subject.lower()

    assert _run(requires_review, {"subject": "Refund request"})
    assert not _run(requires_review, {"subject": "Hello"})


def test_approval_wires_into_tool() -> None:
    """`approval(...)` plugs straight into `@tool(needs_approval=...)`."""

    @tool(needs_approval=approval(lambda subject: "refund" in subject.lower()))
    async def send_email(subject: str, body: str) -> str:
        """Send an email."""
        return f"Sent '{subject}'"

    assert callable(send_email.needs_approval)
    assert _run(send_email.needs_approval, {"subject": "Refund request", "body": "hi"})


def test_approval_unknown_param_raises_key_error() -> None:
    """A predicate parameter that matches no tool argument fails loudly, not silently."""

    @approval
    def requires_review(subjct: str) -> bool:  # typo, on purpose
        return bool(subjct)

    with pytest.raises(KeyError):
        _run(requires_review, {"subject": "x"})
