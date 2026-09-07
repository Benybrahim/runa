from dataclasses import MISSING, dataclass, fields, replace
from typing import Any, Literal

from agents import Agent as BaseAgent
from agents import Runner
from agents.items import TResponseInputItem


@dataclass(frozen=True)
class Subagent:
    agent: type[BaseAgent]
    mode: Literal["handoff", "delegate"]
    tool_name: str | None = None
    tool_description: str | None = None

    def __call__(
        self, *, tool_name: str | None = None, tool_description: str | None = None
    ) -> Subagent:
        return replace(self, tool_name=tool_name, tool_description=tool_description)


class _Mode:
    def __init__(self, mode: Literal["handoff", "delegate"]) -> None:
        self.mode = mode

    def __get__(self, instance: object, owner: type[BaseAgent]) -> Subagent:
        return Subagent(owner, self.mode)


class Agent(BaseAgent):
    handoff = _Mode("handoff")
    delegate = _Mode("delegate")
    model = "gpt-5.4-nano"

    def __init__(self, **kwargs: Any) -> None:
        for f in fields(BaseAgent):
            value = getattr(type(self), f.name, MISSING)
            if value is not MISSING:
                kwargs.setdefault(f.name, value)
        handoffs = list(kwargs.get("handoffs", []))
        tools = list(kwargs.get("tools", []))
        for sub in getattr(type(self), "subagents", []):
            agent = sub.agent()
            if sub.mode == "handoff":
                handoffs.append(agent)
            else:
                tools.append(agent.as_tool(sub.tool_name, sub.tool_description))
        kwargs["handoffs"] = handoffs
        kwargs["tools"] = tools
        super().__init__(**kwargs)
        self.history: list[TResponseInputItem] = []

    async def run(self, message: str) -> str:
        turn_input = [*self.history, {"role": "user", "content": message}]
        result = await Runner.run(self, turn_input)
        self.history = result.to_input_list()
        return result.final_output

    def run_sync(self, message: str) -> str:
        turn_input = [*self.history, {"role": "user", "content": message}]
        result = Runner.run_sync(self, turn_input)
        self.history = result.to_input_list()
        return result.final_output
