"""Agent: a declarative object with behavior and capabilities."""

from typing import Any, ClassVar

from runa.background import Queue
from runa.background import run_later as _run_later
from runa.config import default_provider
from runa.core import Conversation, Run
from runa.runtime import Executor
from runa.tool import Tool

ToolEntry = type[Tool] | Tool


class DuplicateToolName(Exception):
    """Raised when two tools declared on an Agent share a name."""


class UnknownApprovalTool(Exception):
    """Raised when `requires_approval` names a tool not present in `tools`."""


def _resolve_tool(entry: ToolEntry) -> Tool:
    if isinstance(entry, Tool):
        return entry
    if isinstance(entry, type) and issubclass(entry, Tool):
        return entry()
    raise TypeError(f"{entry!r} is not a Tool subclass or instance")


class Agent:
    """Base class for declaring an agent's instructions and capabilities.

    Subclass and set `instructions`, `tools`, and optionally
    `requires_approval` and `model` at the class level. A reader should be
    able to see what an agent can do from its class body alone:

        class SupportAgent(Agent):
            tools = [KnowledgeBase, CreateTicket]

            instructions = '''
            Help customers resolve support issues.
            Create a ticket when the issue cannot be resolved.
            '''
    """

    instructions: ClassVar[str] = ""
    tools: ClassVar[list[ToolEntry]] = []
    requires_approval: ClassVar[list[ToolEntry]] = []
    model: ClassVar[str | None] = None

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        cls.approval_tool_names()  # resolved eagerly so mistakes surface at import time

    @classmethod
    def resolved_tools(cls) -> dict[str, Tool]:
        cached = cls.__dict__.get("_resolved_tools")
        if cached is not None:
            return cached

        resolved: dict[str, Tool] = {}
        for entry in cls.tools:
            resolved_tool = _resolve_tool(entry)
            name = resolved_tool.tool_name()
            if name in resolved:
                raise DuplicateToolName(
                    f"{cls.__name__} declares more than one tool named {name!r}"
                )
            resolved[name] = resolved_tool

        cls._resolved_tools = resolved
        return resolved

    @classmethod
    def approval_tool_names(cls) -> frozenset[str]:
        cached = cls.__dict__.get("_approval_tool_names")
        if cached is not None:
            return cached

        tools = cls.resolved_tools()
        names = {name for name, tool in tools.items() if tool.requires_approval}
        for entry in cls.requires_approval:
            resolved_tool = _resolve_tool(entry)
            name = resolved_tool.tool_name()
            if name not in tools:
                raise UnknownApprovalTool(
                    f"{cls.__name__}.requires_approval names {name!r}, "
                    "which is not declared in `tools`"
                )
            names.add(name)

        result = frozenset(names)
        cls._approval_tool_names = result
        return result

    def before_run(self, run: Run) -> None:
        """Called before execution begins. Override to customize."""

    def plan(self, run: Run) -> None:
        """Called to plan before acting. Override to customize."""

    def review(self, run: Run) -> None:
        """Called to review results before completion. Override to customize."""

    def after_run(self, run: Run) -> None:
        """Called after execution completes. Override to customize."""

    @classmethod
    def run(
        cls,
        input: Any,
        *,
        executor: Executor | None = None,
        conversation: Conversation | None = None,
    ) -> Run:
        """Run this agent against `input` and return the completed Run.

        Uses the app-wide default Provider (see `runa.configure()`) unless
        an `Executor` is given explicitly — the escape hatch for an agent
        that needs a specific provider, strategy, or max_steps.

        Pass `conversation` to continue a prior exchange: its history is
        seeded ahead of `input`, and this Run's messages are folded back
        into it once the Run completes, so the next `.run(..., conversation=
        conversation)` call picks up where this one left off.
        """
        executor = executor or Executor(provider=default_provider())
        return executor.run(cls(), Run(input=input, conversation=conversation))

    @classmethod
    def run_later(
        cls,
        input: Any,
        *,
        executor: Executor | None = None,
        queue: Queue | None = None,
        conversation: Conversation | None = None,
    ) -> Run:
        """Queue this agent's run for background execution. See `Agent.run`."""
        executor = executor or Executor(provider=default_provider())
        run = Run(input=input, conversation=conversation)
        return _run_later(cls(), run, executor, queue=queue)
