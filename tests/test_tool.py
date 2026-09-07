"""Tests for the `@tool` decorator's `guardrail=`/`require_approval=` wiring."""

import asyncio
from collections.abc import Awaitable
from typing import Any, cast

import pytest
from agents import (
    FunctionTool,
    ToolGuardrailFunctionOutput,
    ToolInputGuardrail,
    ToolOutputGuardrail,
)

from runa import guardrail, tool


def _run(
    g: ToolInputGuardrail[Any] | ToolOutputGuardrail[Any], data: Any
) -> ToolGuardrailFunctionOutput:
    """Call a wrapped tool guardrail's function directly, awaiting its always-async wrapper."""
    coro = cast(Awaitable[ToolGuardrailFunctionOutput], g.guardrail_function(data))
    return asyncio.run(coro)


def _tripped(output: ToolGuardrailFunctionOutput) -> bool:
    """Whether a `ToolGuardrailFunctionOutput` halts execution rather than allowing it."""
    return output.behavior["type"] == "raise_exception"


class _Data:
    """A stand-in for `ToolInputGuardrailData`/`ToolOutputGuardrailData`."""

    def __init__(self, tool_arguments: str, output: Any = None) -> None:
        self.context = cast(Any, type("Ctx", (), {"tool_arguments": tool_arguments})())
        self.output = output


@guardrail
def block_args(args: dict) -> bool:
    """Trip when the tool is called with any arguments."""
    return bool(args)


@guardrail
def block_long(output: str) -> bool:
    """Trip when the output is too long."""
    return len(output) > 100


@tool
def bare() -> str:
    """Return a constant string, with no guardrails or approval requirement."""
    return "ok"


def test_bare_tool_has_no_guardrails_or_approval() -> None:
    """`@tool` with no args produces a plain `FunctionTool`."""
    assert isinstance(bare, FunctionTool)
    assert bare.tool_input_guardrails is None
    assert bare.tool_output_guardrails is None
    assert bare.needs_approval is False


def test_guardrail_list_splits_by_binding() -> None:
    """`.tool_input`/`.tool_output`-bound entries land in their matching SDK list."""

    @tool(guardrail=[block_args.tool_input, block_long.tool_output])
    def now() -> str:
        """Return a constant string."""
        return "now"

    assert [g.get_name() for g in now.tool_input_guardrails or []] == ["block_args"]
    assert [g.get_name() for g in now.tool_output_guardrails or []] == ["block_long"]


def test_bare_guardrail_wires_both_sides() -> None:
    """A bare `@guardrail` predicate in the list is wired as both input and output."""

    @tool(guardrail=[block_args])
    def now() -> str:
        """Return a constant string."""
        return "now"

    assert [g.get_name() for g in now.tool_input_guardrails or []] == ["block_args"]
    assert [g.get_name() for g in now.tool_output_guardrails or []] == ["block_args"]


def test_invalid_guardrail_entry_raises() -> None:
    """A `guardrail` entry not bound via `.tool_input`/`.tool_output` is rejected."""
    with pytest.raises(TypeError, match="guardrail entries must be"):

        @tool(guardrail=cast(Any, [lambda value: False]))
        def now() -> str:
            """Return a constant string."""
            return "now"


def test_require_approval_forwards_to_needs_approval() -> None:
    """`require_approval=True` forwards to the SDK's `needs_approval`."""

    @tool(require_approval=True)
    def now() -> str:
        """Return a constant string."""
        return "now"

    assert now.needs_approval is True


def test_tool_input_guardrail_sees_parsed_arguments() -> None:
    """A `.tool_input`-bound predicate receives the tool call's arguments as a parsed dict."""
    bound = block_args.tool_input

    assert _tripped(_run(bound, _Data(tool_arguments='{"x": 1}')))
    assert not _tripped(_run(bound, _Data(tool_arguments="{}")))


def test_tool_output_guardrail_sees_return_value() -> None:
    """A `.tool_output`-bound predicate receives the tool's raw return value."""
    bound = block_long.tool_output

    assert _tripped(_run(bound, _Data(tool_arguments="{}", output="x" * 101)))
    assert not _tripped(_run(bound, _Data(tool_arguments="{}", output="short")))
