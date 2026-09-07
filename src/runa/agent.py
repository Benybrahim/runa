"""Class-based Agent built on the OpenAI Agents SDK."""

from dataclasses import MISSING, dataclass, fields, replace
from typing import Any, Literal

from agents import Agent as BaseAgent
from agents import RunConfig, Runner
from agents.extensions.models.litellm_provider import LitellmProvider
from agents.guardrail import InputGuardrail, OutputGuardrail
from agents.items import TResponseInputItem

_RUN_CONFIG = RunConfig(model_provider=LitellmProvider())

SubagentsList = list["type[Agent] | Subagent"]
SubagentsDict = dict[Literal["handoff", "delegate", "auto"], SubagentsList]


def _flatten_subagents(subagents: SubagentsList | SubagentsDict) -> SubagentsList:
    """Normalize the `subagents` class attribute to the flat list the wiring loop expects.

    Accepts either a plain list (each entry bare, or `.handoff`/`.delegate`-wrapped) or a
    `{"handoff": [...], "delegate": [...], "auto": [...]}` dict, where the key supplies the
    mode for any bare entry.
    """
    if not isinstance(subagents, dict):
        return list(subagents)
    flat: SubagentsList = []
    for mode, subs in subagents.items():
        for sub in subs:
            flat.append(sub if mode == "auto" or isinstance(sub, Subagent) else Subagent(sub, mode))
    return flat


class _Mode:
    def __init__(self, mode: Literal["handoff", "delegate"]) -> None:
        self.mode: Literal["handoff", "delegate"] = mode

    def __get__(self, instance: object, owner: type[Agent]) -> Subagent:
        return Subagent(owner, self.mode)


class Agent(BaseAgent):
    """An Agent whose config comes from class attributes instead of __init__ args."""

    handoff = _Mode("handoff")
    delegate = _Mode("delegate")
    model = "gpt-5.4-nano"

    def __init__(self, **kwargs: Any) -> None:
        """Build kwargs from class attributes and wire up any subagents and guardrails."""
        for f in fields(BaseAgent):
            value = getattr(type(self), f.name, MISSING)
            if value is not MISSING:
                kwargs.setdefault(f.name, value)
        handoffs = list(kwargs.get("handoffs", []))
        tools = list(kwargs.get("tools", []))
        for sub in _flatten_subagents(getattr(type(self), "subagents", [])):
            if isinstance(sub, Subagent):
                agent = sub.agent()
                if sub.mode == "handoff":
                    handoffs.append(agent)
                else:
                    tools.append(agent.as_tool(sub.tool_name, sub.tool_description))
            else:
                agent = sub()
                handoffs.append(agent)
                tools.append(agent.as_tool(None, None))
        kwargs["handoffs"] = handoffs
        kwargs["tools"] = tools
        input_guardrails = list(kwargs.get("input_guardrails", []))
        output_guardrails = list(kwargs.get("output_guardrails", []))
        for g in getattr(type(self), "guardrails", []):
            if isinstance(g, InputGuardrail):
                input_guardrails.append(g)
            elif isinstance(g, OutputGuardrail):
                output_guardrails.append(g)
            else:
                raise TypeError(
                    f"guardrails entries must be @Guardrail.input/@Guardrail.output, "
                    f"got {type(g).__name__}"
                )
        kwargs["input_guardrails"] = input_guardrails
        kwargs["output_guardrails"] = output_guardrails
        super().__init__(**kwargs)
        self.history: list[TResponseInputItem] = []

    async def run(self, message: str) -> str:
        """Run a turn asynchronously, appending it to the conversation history."""
        turn_input = [*self.history, {"role": "user", "content": message}]
        result = await Runner.run(self, turn_input, run_config=_RUN_CONFIG)
        self.history = result.to_input_list()
        return result.final_output

    def run_sync(self, message: str) -> str:
        """Run a turn synchronously, appending it to the conversation history."""
        turn_input = [*self.history, {"role": "user", "content": message}]
        result = Runner.run_sync(self, turn_input, run_config=_RUN_CONFIG)
        self.history = result.to_input_list()
        return result.final_output


@dataclass(frozen=True)
class Subagent:
    """A wired-up subagent, attached as a handoff or a delegate tool."""

    agent: type[Agent]
    mode: Literal["handoff", "delegate"]
    tool_name: str | None = None
    tool_description: str | None = None

    def __call__(
        self, *, tool_name: str | None = None, tool_description: str | None = None
    ) -> Subagent:
        """Return a copy with the tool name/description overridden."""
        return replace(self, tool_name=tool_name, tool_description=tool_description)
