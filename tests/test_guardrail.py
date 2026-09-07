"""Tests for the `Guardrail.input`/`Guardrail.output` wiring in `Agent`."""

import pytest
from agents import GuardrailFunctionOutput

from runa import Agent, Guardrail


@Guardrail.input
def block_topic(ctx, agent, input) -> GuardrailFunctionOutput:  # noqa: A002, ANN001
    """Allow every input; used across tests."""
    return GuardrailFunctionOutput(output_info=None, tripwire_triggered=False)


@Guardrail.output
def block_profanity(ctx, agent, output) -> GuardrailFunctionOutput:  # noqa: ANN001
    """Allow every output; used across tests."""
    return GuardrailFunctionOutput(output_info=None, tripwire_triggered=False)


def test_guardrails_split_into_input_and_output() -> None:
    """A `guardrails` list is sorted into `input_guardrails`/`output_guardrails` by type."""

    class Support(Agent):
        name = "Support"
        instructions = "support"
        guardrails = [block_topic, block_profanity]

    agent = Support()

    assert agent.input_guardrails == [block_topic]
    assert agent.output_guardrails == [block_profanity]


def test_no_guardrails_leaves_both_lists_empty() -> None:
    """An agent with no `guardrails` attribute wires up cleanly."""

    class Support(Agent):
        name = "Support"
        instructions = "support"

    agent = Support()

    assert agent.input_guardrails == []
    assert agent.output_guardrails == []


def test_invalid_guardrail_entry_raises() -> None:
    """A `guardrails` entry that isn't an `InputGuardrail`/`OutputGuardrail` is rejected."""

    class Support(Agent):
        name = "Support"
        instructions = "support"
        guardrails = [lambda ctx, agent, input: None]

    with pytest.raises(TypeError, match="guardrails entries must be"):
        Support()


def test_explicit_input_guardrails_kwarg_merges_with_class_attribute() -> None:
    """An explicit `input_guardrails` kwarg is preserved alongside the `guardrails` attribute."""

    class Support(Agent):
        name = "Support"
        instructions = "support"
        guardrails = [block_profanity]

    agent = Support(input_guardrails=[block_topic])

    assert agent.input_guardrails == [block_topic]
    assert agent.output_guardrails == [block_profanity]
