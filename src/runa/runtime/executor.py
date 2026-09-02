"""Executor: drives a Strategy against a Run, emitting Events as it acts."""

from typing import Any

from runa.agent import Agent
from runa.core import EventType, Message, Role, Run, ToolCall
from runa.runtime.provider import Provider
from runa.runtime.strategy import (
    Action,
    CallModel,
    CallTool,
    Complete,
    DefaultStrategy,
    Fail,
    Strategy,
)


class Executor:
    """Drives a Strategy against a Run.

    Seeds the initial messages, calls the model, executes tools, and applies
    the Strategy's decisions until the Run reaches a terminal status.
    """

    def __init__(
        self,
        provider: Provider,
        strategy: Strategy | None = None,
        *,
        max_steps: int = 50,
    ) -> None:
        self.provider = provider
        self.strategy = strategy or DefaultStrategy()
        self.max_steps = max_steps

    def run(self, agent: Agent, run: Run) -> Run:
        self._seed(agent, run)
        run.start()
        agent.before_run(run)

        steps = 0
        while not run.is_terminal:
            if steps >= self.max_steps:
                run.fail(error=f"exceeded max_steps ({self.max_steps})")
                break
            steps += 1

            try:
                action = self.strategy.step(run)
                self._apply(agent, run, action)
            except Exception as exc:  # convert into a failed Run, not a crash
                run.fail(error=str(exc))
                break

        agent.after_run(run)
        return run

    def _seed(self, agent: Agent, run: Run) -> None:
        if agent.instructions:
            run.add_message(Message(role=Role.SYSTEM, content=agent.instructions))
        run.add_message(Message(role=Role.USER, content=str(run.input)))

    def _apply(self, agent: Agent, run: Run, action: Action) -> None:
        if isinstance(action, CallModel):
            self._call_model(agent, run)
        elif isinstance(action, CallTool):
            self._call_tool(agent, run, action.tool_call)
        elif isinstance(action, Complete):
            run.complete(result=action.result)
        elif isinstance(action, Fail):
            run.fail(error=action.error)
        else:
            raise TypeError(f"unknown action: {action!r}")

    def _call_model(self, agent: Agent, run: Run) -> None:
        run.emit(EventType.MODEL_CALLED)
        schemas = self._tool_schemas(agent)
        message = self.provider.complete(
            messages=run.messages, tools=schemas, model=agent.model
        )
        run.add_message(message)
        run.emit(EventType.MODEL_RESPONDED)

    def _call_tool(self, agent: Agent, run: Run, tool_call: ToolCall) -> None:
        tool = agent.resolved_tools()[tool_call.name]
        run.emit(EventType.TOOL_CALLED, tool=tool_call.name, tool_call_id=tool_call.id)
        tool_call.result = tool.call(**tool_call.arguments)
        run.add_message(
            Message(
                role=Role.TOOL,
                content=str(tool_call.result),
                tool_call_id=tool_call.id,
            )
        )
        run.emit(
            EventType.TOOL_COMPLETED, tool=tool_call.name, tool_call_id=tool_call.id
        )

    def _tool_schemas(self, agent: Agent) -> list[dict[str, Any]]:
        return [
            {
                "name": name,
                "description": tool.tool_description(),
                "parameters": tool.schema(),
            }
            for name, tool in agent.resolved_tools().items()
        ]
