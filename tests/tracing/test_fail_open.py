"""Tests for tracing's fail-open guarantee: a broken exporter must never break an agent run."""

import agents.tracing as at

from runa import Trace
from runa.agent import Agent
from runa.tracing import observe
from runa.tracing.processor import processor


class _BrokenExporter:
    """An exporter that always raises, to prove tracing failures don't propagate."""

    def export(self, trace: Trace) -> None:
        """Raise unconditionally."""
        raise RuntimeError("storage is down")


def test_broken_exporter_does_not_raise_out_of_on_trace_end() -> None:
    """A trace still finishes and is still cached for pickup even if every exporter fails."""
    with observe(exporter=_BrokenExporter()), at.trace("T") as sdk_trace, at.agent_span("T"):
        pass

    trace = processor.pop_finished(sdk_trace.trace_id)

    assert trace is not None
    assert trace.spans


def test_agent_run_sync_completes_even_when_the_exporter_fails() -> None:
    """`Agent.run_sync` still returns a completed `Run` when the tracing exporter raises.

    Drives a real `Runner.run_sync()` call (via `ScriptedModel`) rather than faking the SDK's
    result, so `on_trace_end` genuinely fires and `_BrokenExporter.export` genuinely runs — this
    is what proves the failure is actually contained, not just that a disconnected fake passed.
    """
    from agents.testing.model import ScriptedModel
    from openai.types.responses import ResponseOutputMessage, ResponseOutputText

    class Researcher(Agent):
        name = "Researcher"
        instructions = "You research topics."
        model = ScriptedModel(
            steps=[
                [
                    ResponseOutputMessage(
                        id="msg_1",
                        role="assistant",
                        status="completed",
                        type="message",
                        content=[ResponseOutputText(text="ok", type="output_text", annotations=[])],
                    )
                ]
            ],
            emit_traces=True,
        )

    with observe(exporter=_BrokenExporter()):
        run = Researcher().run_sync("hi")

    assert run.status == "completed"
    assert run.output == "ok"
    assert run.trace.spans
