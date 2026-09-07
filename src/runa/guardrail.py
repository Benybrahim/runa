"""Guardrail namespace for tagging input/output guardrail functions."""

from agents import input_guardrail, output_guardrail


class Guardrail:
    """Namespace for the `@Guardrail.input` / `@Guardrail.output` decorators."""

    input = staticmethod(input_guardrail)
    output = staticmethod(output_guardrail)


__all__ = ["Guardrail"]
