"""Tests for the handoff / delegate / auto subagent wiring in `Agent`."""

import asyncio
from dataclasses import dataclass
from typing import Any

from agents import FunctionTool, RunContextWrapper

from runa import Agent
from runa.agent import Subagent


def _handoff_names(agent: Agent) -> list[str]:
    """Names of an agent's handoffs, narrowed away from the raw `Handoff` union member."""
    return [h.name for h in agent.handoffs if isinstance(h, Agent)]


def _tool_names(agent: Agent) -> list[str]:
    """Names of an agent's tools, narrowed away from the raw `Tool` union members."""
    return [t.name for t in agent.tools if isinstance(t, FunctionTool)]


class Researcher(Agent):
    """A subagent used across tests."""

    name = "Researcher"
    instructions = "You research topics."


class Translator(Agent):
    """Another subagent used across tests."""

    name = "Translator"
    instructions = "You translate text."


def test_handoff_adds_only_to_handoffs() -> None:
    """`.handoff` wires the subagent as a handoff, not a tool."""

    class Main(Agent):
        name = "Main"
        instructions = "main"
        subagents = [Researcher.handoff]

    agent = Main()

    assert _handoff_names(agent) == ["Researcher"]
    assert agent.tools == []


def test_delegate_adds_only_to_tools() -> None:
    """`.delegate` wires the subagent as a tool, not a handoff."""

    class Main(Agent):
        name = "Main"
        instructions = "main"
        subagents = [Researcher.delegate]

    agent = Main()

    assert agent.handoffs == []
    assert _tool_names(agent) == [Researcher().as_tool(None, None).name]


def test_delegate_tool_name_and_description_override() -> None:
    """Calling a `.delegate` subagent overrides the generated tool's name/description."""

    class Main(Agent):
        name = "Main"
        instructions = "main"
        subagents = [Researcher.delegate(tool_name="do_research", tool_description="Look into it.")]

    agent = Main()

    (tool,) = agent.tools
    assert isinstance(tool, FunctionTool)
    assert tool.name == "do_research"
    assert tool.description == "Look into it."


def test_bare_subagent_wires_both_handoff_and_delegate() -> None:
    """A subagent listed without `.handoff`/`.delegate` lets the model pick either mode."""

    class Main(Agent):
        name = "Main"
        instructions = "main"
        subagents = [Researcher]

    agent = Main()

    assert _handoff_names(agent) == ["Researcher"]
    assert _tool_names(agent) == [Researcher().as_tool(None, None).name]


def test_mixed_modes_wire_independently() -> None:
    """Handoff and delegate subagents in the same list don't interfere with each other."""

    class Main(Agent):
        name = "Main"
        instructions = "main"
        subagents = [Researcher.handoff, Translator.delegate]

    agent = Main()

    assert _handoff_names(agent) == ["Researcher"]
    assert _tool_names(agent) == [Translator().as_tool(None, None).name]


def test_no_subagents_leaves_handoffs_and_tools_empty() -> None:
    """An agent with no `subagents` attribute wires up cleanly."""

    class Main(Agent):
        name = "Main"
        instructions = "main"

    agent = Main()

    assert agent.handoffs == []
    assert agent.tools == []


def test_dict_subagents_wire_by_key() -> None:
    """A `{"handoff": [...], "delegate": [...], "auto": [...]}` dict wires each bucket."""

    class Helper(Agent):
        name = "Helper"
        instructions = "helper"

    class Main(Agent):
        name = "Main"
        instructions = "main"
        subagents = {
            "handoff": [Researcher],
            "delegate": [Translator],
            "auto": [Helper],
        }

    agent = Main()

    assert sorted(_handoff_names(agent)) == ["Helper", "Researcher"]
    assert sorted(_tool_names(agent)) == sorted(
        [Translator().as_tool(None, None).name, Helper().as_tool(None, None).name]
    )


def test_dict_subagents_delegate_bucket_keeps_tool_overrides() -> None:
    """A `.delegate(...)` override still applies inside the dict format's `delegate` bucket."""

    class Main(Agent):
        name = "Main"
        instructions = "main"
        subagents = {
            "delegate": [
                Researcher.delegate(tool_name="do_research", tool_description="Look into it.")
            ]
        }

    agent = Main()

    (tool,) = agent.tools
    assert isinstance(tool, FunctionTool)
    assert tool.name == "do_research"
    assert tool.description == "Look into it."


def test_subagent_descriptor_returns_fresh_immutable_instance() -> None:
    """Each access to `.handoff`/`.delegate` is a new `Subagent`; overrides don't mutate it."""
    first = Researcher.handoff
    second = Researcher.handoff

    assert first is not second
    assert first == second
    assert isinstance(first, Subagent)

    overridden = first(tool_name="custom", tool_description="d")
    assert overridden.tool_name == "custom"
    assert first.tool_name is None, "overriding a copy must not mutate the original"


def test_class_attributes_seed_init_defaults() -> None:
    """Class attributes like `name`/`instructions`/`model` become constructor defaults."""
    agent = Researcher()

    assert agent.name == "Researcher"
    assert agent.instructions == "You research topics."
    assert agent.model == "gpt-5.4-nano"


def test_explicit_kwarg_overrides_class_attribute() -> None:
    """An explicit constructor kwarg wins over the class attribute default."""
    agent = Researcher(model="gpt-4.1")

    assert agent.model == "gpt-4.1"


def test_history_starts_empty() -> None:
    """A freshly constructed agent has no conversation history yet."""
    agent = Researcher()

    assert agent.history == []


@dataclass
class _Ctx:
    """A minimal run context used by the dynamic-instructions tests below."""

    label: str


def _single_arg_instructions(context: _Ctx) -> str:
    return f"context={context.label}"


def _two_arg_instructions(context: RunContextWrapper[_Ctx], agent: Any) -> str:
    return f"{agent.name}:{context.context.label}"


def test_single_arg_instructions_resolves_from_run_context() -> None:
    """A one-parameter `(context) -> str` `instructions` is adapted to the SDK's 2-arg shape."""

    class Dynamic(Agent):
        name = "Dynamic"
        instructions = _single_arg_instructions  # pyright: ignore[reportAssignmentType]

    agent = Dynamic()

    prompt = asyncio.run(agent.get_system_prompt(RunContextWrapper(context=_Ctx(label="hi"))))

    assert prompt == "context=hi"


def test_two_arg_instructions_still_supported() -> None:
    """A native SDK-style `(context, agent) -> str` `instructions` passes through unadapted."""

    class Dynamic(Agent):
        name = "Dynamic"
        instructions = _two_arg_instructions

    agent = Dynamic()

    prompt = asyncio.run(agent.get_system_prompt(RunContextWrapper(context=_Ctx(label="hi"))))

    assert prompt == "Dynamic:hi"


def test_string_instructions_pass_through_unchanged() -> None:
    """Plain string instructions are unaffected by the dynamic-instructions adapter."""
    prompt = asyncio.run(Researcher().get_system_prompt(RunContextWrapper(context=None)))

    assert prompt == "You research topics."
