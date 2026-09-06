"""Agent: a declarative object with behavior and capabilities."""

import asyncio
from collections.abc import Callable
from typing import Any, ClassVar

from runa.application import application
from runa.background import Queue
from runa.background import run_later as _run_later
from runa.core import Conversation, Run, RunStatus, ToolCall
from runa.runtime import AsyncExecutor, Executor, StreamChunk
from runa.tool import Tool

ToolEntry = type[Tool] | Tool

Policy = Callable[[Run, ToolCall], bool]


class AgentStream:
    """What `Agent.run_stream()` returns: an async iterator of `StreamChunk`s.

    `run` is the exact `Run` object `AsyncExecutor` is advancing, available
    immediately rather than only once exhausted (contrast `Stream.message`/
    `AsyncStream.message` in `runtime/provider.py`/`runtime/async_provider.py`,
    which can't be read until their stream is drained): Execution writes
    messages, events, and state onto it as it goes, so it fills in as you
    iterate and reaches its final status and result once the stream ends,
    the same `Run` `Agent.run_async()` would have returned for the same
    call. `run_stream()` is another way to observe that Execution, not a
    second one.
    """

    def __init__(
        self,
        run: Run,
        task: "asyncio.Task[Run]",
        queue: "asyncio.Queue[StreamChunk | None]",
    ) -> None:
        self.run = run
        self._task = task
        self._queue = queue

    def __aiter__(self) -> "AgentStream":
        return self

    async def __anext__(self) -> StreamChunk:
        chunk = await self._queue.get()
        if chunk is None:
            await self._task  # re-raise if driving the Run itself failed
            raise StopAsyncIteration
        return chunk


class DuplicateToolName(Exception):
    """Raised when two tools declared on an Agent share a name."""


def _resolve_tool(entry: ToolEntry) -> Tool:
    if isinstance(entry, Tool):
        return entry
    if isinstance(entry, type) and issubclass(entry, Tool):
        return entry()
    raise TypeError(f"{entry!r} is not a Tool subclass or instance")


class Agent:
    """Base class for declaring an agent's instructions and capabilities.

    Subclass and set `instructions`, `tools`, and optionally `model` at the
    class level. A reader should be able to see what an agent can do from
    its class body alone:

        class SupportAgent(Agent):
            tools = [KnowledgeBase, CreateTicket]

            instructions = '''
            Help customers resolve support issues.
            Create a ticket when the issue cannot be resolved.
            '''
    """

    # Identity
    name: ClassVar[str | None] = None
    version: ClassVar[str | None] = None

    # Declaration
    instructions: ClassVar[str] = ""
    model: ClassVar[str | None] = None
    tools: ClassVar[list[ToolEntry]] = []
    delegations: ClassVar[list["DelegationEntry"]] = []

    # Constraints
    policies: ClassVar[list[Policy]] = []

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        cls.resolved_tools()  # resolved eagerly so mistakes surface at import time

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
        for entry in cls.delegations:
            resolved_tool = _resolve_delegation(entry)
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
        """Names of resolved tools that require approval before running.

        Approval is a property of the Tool being called, not something an
        Agent declares separately: set `requires_approval = True` on the
        Tool itself (or `@tool(requires_approval=True)`), and any Agent
        that declares it inherits the gate automatically.
        """
        cached = cls.__dict__.get("_approval_tool_names")
        if cached is not None:
            return cached

        result = frozenset(
            name
            for name, tool in cls.resolved_tools().items()
            if tool.requires_approval
        )
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

    # Lifecycle

    def before_run(self, run: Run) -> None:
        """Called once before the ReAct loop starts. Override to customize.

        Use this to surface application State the model needs to see (see
        `runtime/_shared.seed_run`), not to decide what happens next: that
        is the Strategy's job, not the Agent's.
        """

    def after_run(self, run: Run) -> None:
        """Called after execution completes. Override to customize."""

    # Execution API

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
    def run_stream(
        cls,
        input: Any,
        *,
        executor: AsyncExecutor | None = None,
        conversation: Conversation | None = None,
    ) -> AgentStream:
        """Run this agent against `input`, observing the model's output as it streams.

        `run()`, `run_async()`, and `run_stream()` are different interfaces
        to the same Execution: this one drives the exact same `AsyncExecutor`
        loop as `run_async`, just with `AsyncExecutor.run(..., on_chunk=...)`
        supplied internally to bridge each `StreamChunk` into an async
        iterator as it arrives, instead of only returning the completed
        `Run`. The `Run` this Execution produces is still there afterward,
        as `.run` on the returned `AgentStream`, and it is identical to what
        `run_async()` would have returned for the same call:

            stream = ResearchAgent.run_stream("Research fusion energy.")
            async for chunk in stream:
                print(chunk.text, end="")
            stream.run.result

        This first version only streams the model's output, the same
        `StreamChunk`s `on_chunk` already delivers; it does not yet stream
        tool calls, state changes, or other Run events.

        Async-only: requires the app-wide default AsyncProvider (or the
        `executor` given explicitly) to satisfy `AsyncStreamingProvider`,
        the same requirement `AsyncExecutor.run`'s `on_chunk` has.
        """
        executor = executor or AsyncExecutor(provider=application.async_provider)
        run = Run(input=input, conversation=conversation)
        queue: asyncio.Queue[StreamChunk | None] = asyncio.Queue()

        async def on_chunk(chunk: StreamChunk) -> None:
            await queue.put(chunk)

        async def drive() -> Run:
            try:
                return await executor.run(cls(), run, on_chunk=on_chunk)
            finally:
                await queue.put(None)

        task = asyncio.create_task(drive())
        return AgentStream(run, task, queue)

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


class _BaseDelegateAgent(Tool):
    """Shared machinery for `DelegateAgent`/`AsyncDelegateAgent` (`Agent.delegations`).

    Every delegation exposes the same schema regardless of outcome: `input`
    (what to hand the sub-agent) plus an optional `transfer` flag the model
    can set to hand off control of the whole Run to the sub-agent instead of
    getting an answer back (see `Executor._transfer`). Only `__init__`/
    `call()` differ between the sync and async subclasses (each types
    `executor` as its own `Executor`/`AsyncExecutor`, not the union both
    would need here, so `self._executor.run(...)` resolves to one concrete
    return type rather than `Run | Coroutine[..., Run]`); everything else
    about being a delegation is identical.
    """

    _agent_cls: type[Agent]
    last_run: Run | None
    _parent_run_id: str | None

    def bind_parent_run_id(self, run_id: str) -> None:
        self._parent_run_id = run_id

    def new_agent_instance(self) -> Agent:
        """A fresh instance of the delegated Agent (see `DelegatesToAgent`).

        Used only for a `transfer=true` call: `Executor._transfer` swaps the
        active Agent to this instance instead of running `call()`.
        """
        return self._agent_cls()

    def schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "input": {"type": "string"},
                "transfer": {
                    "type": "boolean",
                    "description": (
                        "Set true to hand off the conversation to this agent "
                        "instead of returning its answer."
                    ),
                },
            },
            "required": ["input"],
        }


class DelegateAgent(_BaseDelegateAgent):
    """Runs an Agent as a delegation: the Return outcome for `Agent.delegations`.

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
        self, agent_cls: type[Agent], *, executor: Executor | None = None
    ) -> None:
        self._agent_cls = agent_cls
        self.name = agent_cls.agent_name()
        self.description = agent_cls.instructions
        self._executor = executor
        self.last_run = None
        self._parent_run_id = None

    def call(self, input: str, transfer: bool = False) -> Any:
        # `transfer` is never True here: Executor._call_tool intercepts a
        # transfer=true call before call() would run (see DelegatesToAgent).
        # It's still an accepted parameter so tool_call.arguments (which may
        # explicitly carry transfer=false) can always be splatted straight
        # into call() without a KeyError.
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


class AsyncDelegateAgent(_BaseDelegateAgent):
    """The async counterpart to `DelegateAgent`. See its docstring.

    `DelegateAgent.call()` is a plain function, so under `AsyncExecutor` it
    still works via `asyncio.to_thread` (one thread per delegate, not true
    concurrency). This class's `call()` is `async def` and delegates through
    `AsyncExecutor` instead, so when a model turn requests several sub-agents
    at once, `AsyncExecutor`'s existing `asyncio.gather` batching (see its
    docstring) runs them as genuine concurrent async I/O. Only usable with
    `AsyncExecutor`; like any async-only tool, `Executor` rejects it outright
    rather than mishandling it silently.
    """

    def __init__(
        self, agent_cls: type[Agent], *, executor: AsyncExecutor | None = None
    ) -> None:
        self._agent_cls = agent_cls
        self.name = agent_cls.agent_name()
        self.description = agent_cls.instructions
        self._executor = executor
        self.last_run = None
        self._parent_run_id = None

    async def call(self, input: str, transfer: bool = False) -> Any:
        # See DelegateAgent.call() for why `transfer` is accepted but unused.
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


def _resolve_delegation(entry: "DelegationEntry") -> Tool:
    if isinstance(entry, _BaseDelegateAgent):
        return entry
    if isinstance(entry, type) and issubclass(entry, Agent):
        return DelegateAgent(entry)
    raise TypeError(
        f"{entry!r} is not an Agent subclass or "
        "DelegateAgent/AsyncDelegateAgent instance"
    )


DelegationEntry = type[Agent] | DelegateAgent | AsyncDelegateAgent
