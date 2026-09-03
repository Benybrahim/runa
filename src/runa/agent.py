"""Agent: a declarative object with behavior and capabilities."""

from typing import Any, ClassVar

from runa.background import Queue
from runa.background import run_later as _run_later
from runa.config import default_async_provider, default_provider
from runa.core import Conversation, Run, RunStatus
from runa.runtime import AsyncExecutor, Executor
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

    def review(self, run: Run) -> Any | None:
        """Called to review the draft result before completion.

        Override to customize. Return a value to replace the Strategy's
        draft result with it (manifesto §6's "reflection"); return `None`
        (the default — an override that falls off the end returns `None`
        automatically) to leave it as the Strategy decided.
        """
        return None

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
    async def run_async(
        cls,
        input: Any,
        *,
        executor: AsyncExecutor | None = None,
        conversation: Conversation | None = None,
    ) -> Run:
        """Run this agent against `input` using an `AsyncExecutor`. See `Agent.run`.

        Uses the app-wide default AsyncProvider (`runa.configure(provider=...,
        async_provider=...)`) unless an `AsyncExecutor` is given explicitly.
        Independent tool calls the model asks for in one turn run
        concurrently — see `AsyncExecutor` for the exact rule.
        """
        executor = executor or AsyncExecutor(provider=default_async_provider())
        return await executor.run(cls(), Run(input=input, conversation=conversation))

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

    @classmethod
    def as_tool(
        cls,
        *,
        name: str | None = None,
        description: str | None = None,
        executor: Executor | None = None,
    ) -> Tool:
        """Wrap this Agent as a Tool another Agent can call (manifesto §6).

        A parent agent delegates by declaring the sub-agent as an ordinary
        tool — `tools = [ResearchAgent.as_tool()]` — no new Strategy needed:
        `DefaultStrategy`'s existing tool-use loop already covers it once an
        Agent can be handed in as a Tool.
        """
        return DelegateTool(cls, name=name, description=description, executor=executor)


class DelegateTool(Tool):
    """Runs an Agent as a Tool call — the delegation strategy from manifesto §6.

    `call()` runs the wrapped Agent synchronously against `input`, using the
    app-wide default Provider (`runa.configure()`) unless an `executor` is
    given, and returns its `Run.result` — the same value the sub-agent's own
    `.run()` would return. A run that doesn't complete raises, which the
    parent's `Executor` turns into an ordinary `TOOL_FAILED` event, so a
    delegate's failure is visible the same way any other tool's is.

    The sub-agent's own `Run` isn't threaded into the parent Run's event log
    — the two are separate executions — but it stays reachable on
    `self.last_run` after each call, as the escape hatch for inspecting a
    delegated run directly (manifesto §15), e.g. `timeline(tool.last_run)`.
    """

    def __init__(
        self,
        agent_cls: type[Agent],
        *,
        name: str | None = None,
        description: str | None = None,
        executor: Executor | None = None,
    ) -> None:
        self._agent_cls = agent_cls
        self.name = name or agent_cls.__name__
        self.description = description or agent_cls.instructions
        self._executor = executor
        self.last_run: Run | None = None

    def call(self, input: str) -> Any:
        executor = self._executor or Executor(provider=default_provider())
        run = executor.run(self._agent_cls(), Run(input=input))
        self.last_run = run
        if run.status != RunStatus.COMPLETED:
            raise RuntimeError(
                f"delegated run to {self.tool_name()} did not complete: {run.status}"
            )
        return run.result

    def schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"input": {"type": "string"}},
            "required": ["input"],
        }
