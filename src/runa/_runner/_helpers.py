"""_helpers.py: low-level per-turn helpers — model/instruction resolution, tool/handoff lookup."""

from __future__ import annotations

import inspect
from typing import Any

from runa._models import Model, ModelProvider
from runa._types import ModelSettings, RunContextWrapper
from runa.handoff import Handoff
from runa.tool import FunctionTool


def _normalized_handoffs(handoffs: list[Any]) -> dict[str, Handoff]:
    """Map each handoff's tool name to its `Handoff`, wrapping a bare `Agent` if given one."""
    result: dict[str, Handoff] = {}
    for entry in handoffs:
        handoff = entry if isinstance(entry, Handoff) else Handoff.from_agent(entry)
        result[handoff.tool_name] = handoff
    return result


async def _agent_tools(agent: Any) -> list[FunctionTool]:
    """This agent's own `tools`, plus whatever its `mcp_servers` currently list."""
    tools = list(getattr(agent, "tools", []))
    for server in getattr(agent, "mcp_servers", []):
        tools.extend(await server.list_tools())
    return tools


def _find_tool(tools: list[Any], name: str) -> FunctionTool | None:
    for candidate in tools:
        if isinstance(candidate, FunctionTool) and candidate.name == name:
            return candidate
    return None


async def _maybe_await(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value


async def _needs_approval(
    tool: FunctionTool, context_wrapper: RunContextWrapper, args: dict[str, Any], call_id: str
) -> bool:
    if isinstance(tool.needs_approval, bool):
        return tool.needs_approval
    return bool(await _maybe_await(tool.needs_approval(context_wrapper, args, call_id)))


def _model_settings(agent: Any) -> ModelSettings:
    settings = getattr(agent, "model_settings", None)
    return settings if isinstance(settings, ModelSettings) else ModelSettings()


def _resolve_model(agent: Any, model_provider: ModelProvider) -> Model:
    return (
        agent.model if not isinstance(agent.model, str) else model_provider.get_model(agent.model)
    )


async def _resolve_instructions(agent: Any, context_wrapper: RunContextWrapper) -> str | None:
    """Resolve `agent.instructions`: a string passes through, a callable is called and awaited."""
    instructions = getattr(agent, "instructions", None)
    if not callable(instructions):
        return instructions
    return await _maybe_await(instructions(context_wrapper, agent))


__all__ = [
    "_agent_tools",
    "_find_tool",
    "_maybe_await",
    "_model_settings",
    "_needs_approval",
    "_normalized_handoffs",
    "_resolve_instructions",
    "_resolve_model",
]
