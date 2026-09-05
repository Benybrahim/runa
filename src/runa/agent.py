"""Agent: a declarative object with behavior and capabilities."""

from collections.abc import Callable
from typing import Any, ClassVar

from runa.application import application
from runa.background import Queue
from runa.background import run_later as _run_later
from runa.core import Conversation, Run, RunStatus, ToolCall
from runa.runtime import AsyncExecutor, Executor
from runa.tool import Tool

ToolEntry = type[Tool] | Tool

Policy = Callable[[Run, ToolCall], bool]


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
    policies: ClassVar[list[Policy]] = []
    model: ClassVar[str | None] = None
    name: ClassVar[str | None] = None
    version: ClassVar[str | None] = None

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        cls.approval_tool_names()  # resolved eagerly so mistakes surface at import time

    @classmethod
    def agent_name(cls) -> str:
        """Stable identity stamped onto every Run this Agent produces.

        Defaults to the class name, same fallback `Tool.tool_name()` uses,
        so provenance (architecture.md §14) works without any
        configuration; override `name` when the class name isn't the
        identity you want persisted (e.g. across a rename).
        """
        return cls.name or cls.__name__

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

    def check_policies(self, run: Run, tool_call: ToolCall) -> bool:
        """Run declared policies against a pending tool call.

        Returns False if any policy vetoes the call: a programmatic
        allow/deny check the Executor runs before a gated call can even
        reach approval, so a call can be blocked without ever routing to a
        human (architecture.md §3's Decision -> Capability -> Policy ->
        Approval -> Action -> Effect chain). Compare `requires_approval`,
        which always defers to a human.
        """
        return all(policy(run, tool_call) for policy in type(self).policies)

    def before_run(self, run: Run) -> None:
        """Called before execution begins. Override to customize."""

    def plan(self, run: Run) -> None:
        """Called to plan before acting. Override to customize."""

    def review(self, run: Run) -> Any | None:
        """Called to review the draft result before completion.

        Override to customize. Return a value to replace the Strategy's
        draft result with it (manifesto §6's "reflection"); return `None`
        (the default; an override that falls off the end returns `None`
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
        an `Executor` is given explicitly: the escape hatch for an agent
        that needs a specific provider, strategy, or max_steps.

        Pass `conversation` to continue a prior exchange: its history is
        seeded ahead of `input`, and this Run's messages are folded back
        into it once the Run completes, so the next `.run(..., conversation=
        conversation)` call picks up where this one left off.
        """
        executor = executor or Executor(provider=application.provider)
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
        concurrently; see `AsyncExecutor` for the exact rule.
        """
        executor = executor or AsyncExecutor(provider=application.async_provider)
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
        executor = executor or Executor(provider=application.provider)
        run = Run(input=input, conversation=conversation)
        return _run_later(cls(), run, executor, queue=queue)

    @classmethod
    def as_tool(
        cls,
        *,
        name: str | None = None,
        description: str | None = None,
        executor: Executor | None = None,
    ) -> "DelegateTool":
        """Wrap this Agent as a Tool another Agent can call (manifesto §6).

        A parent agent delegates by declaring the sub-agent as an ordinary
        tool (`tools = [ResearchAgent.as_tool()]`), no new Strategy needed:
        `DefaultStrategy`'s existing tool-use loop already covers it once an
        Agent can be handed in as a Tool. For a parent driven by
        `AsyncExecutor`/`run_async()`, see `as_async_tool()`.
        """
        return DelegateTool(cls, name=name, description=description, executor=executor)

    @classmethod
    def as_async_tool(
        cls,
        *,
        name: str | None = None,
        description: str | None = None,
        executor: AsyncExecutor | None = None,
    ) -> "AsyncDelegateTool":
        """Wrap this Agent as a Tool for a parent run via AsyncExecutor/
        `run_async()`, the async counterpart to `as_tool()`.

        `DelegateTool.call()` is a plain function, so under AsyncExecutor it
        runs via `asyncio.to_thread` (one thread per delegate, not true
        concurrency). `AsyncDelegateTool.call()` is `async def` and delegates
        through `AsyncExecutor` instead, so when a model turn requests
        several sub-agents at once, AsyncExecutor's existing `asyncio.gather`
        batching (see its docstring) runs them as genuine concurrent async
        I/O. Only usable with `AsyncExecutor`; like any async-only tool,
        `Executor` rejects it outright rather than mishandling it silently.
        """
        return AsyncDelegateTool(
            cls, name=name, description=description, executor=executor
        )


class DelegateTool(Tool):
    """Runs an Agent as a Tool call: the delegation strategy from manifesto §6.

    `call()` runs the wrapped Agent synchronously against `input`, using the
    app-wide default Provider (`runa.configure()`) unless an `executor` is
    given, and returns its `Run.result`, the same value the sub-agent's own
    `.run()` would return. A run that doesn't complete raises, which the
    parent's `Executor` turns into an ordinary `TOOL_FAILED` event, so a
    delegate's failure is visible the same way any other tool's is.

    The sub-agent's own `Run` isn't threaded into the parent Run's event log
    (the two are separate executions), but it stays reachable on
    `self.last_run` after each call, as the escape hatch for inspecting a
    delegated run directly (manifesto §15), e.g. `timeline(tool.last_run)`.
    Its `parent_run_id` also records the parent Run's id (architecture.md
    §15), so the lineage survives being persisted and read back later, not
    just while `self` stays in memory. See `ParentRunAware`.
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
        self._parent_run_id: str | None = None

    def bind_parent_run_id(self, run_id: str) -> None:
        self._parent_run_id = run_id

    def call(self, input: str) -> Any:
        executor = self._executor or Executor(provider=application.provider)
        run = executor.run(
            self._agent_cls(), Run(input=input, parent_run_id=self._parent_run_id)
        )
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


class AsyncDelegateTool(Tool):
    """The async counterpart to `DelegateTool`. See `Agent.as_async_tool()`.

    `call()` is `async def` and runs the wrapped Agent through an
    `AsyncExecutor`, using the app-wide default AsyncProvider
    (`runa.configure(async_provider=...)`) unless an `executor` is given.
    Otherwise identical to `DelegateTool`: `run.result` becomes the tool's
    output, a non-completed sub-run raises (surfacing as an ordinary
    `TOOL_FAILED` event on the parent), and the sub-agent's own `Run` stays
    reachable on `self.last_run` for direct inspection (manifesto §15), with
    `parent_run_id` recording the lineage (see `DelegateTool`).
    """

    def __init__(
        self,
        agent_cls: type[Agent],
        *,
        name: str | None = None,
        description: str | None = None,
        executor: AsyncExecutor | None = None,
    ) -> None:
        self._agent_cls = agent_cls
        self.name = name or agent_cls.__name__
        self.description = description or agent_cls.instructions
        self._executor = executor
        self.last_run: Run | None = None
        self._parent_run_id: str | None = None

    def bind_parent_run_id(self, run_id: str) -> None:
        self._parent_run_id = run_id

    async def call(self, input: str) -> Any:
        executor = self._executor or AsyncExecutor(provider=application.async_provider)
        run = await executor.run(
            self._agent_cls(), Run(input=input, parent_run_id=self._parent_run_id)
        )
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
