"""judge.py: semantic evaluation via LLM-as-judge (manifesto §12).

`Expectation`'s structural checks in `harness.py` (`to_be_completed`,
`to_have_called`, `to_contain`, ...) verify facts about a Run's shape:
"tests verify invariants." A `Judge` verifies something a structural check
can't: whether the agent's answer was actually helpful, factual, or free of
invented claims: "evaluations measure behavior."

A Judge grades a Run by sending its transcript through the same `Provider`
contract the Run itself executed with, rather than a separate model client
(manifesto §17): no new integration to configure, and whatever Provider an
app already set up via `runa.configure()` works here too.
"""

from dataclasses import dataclass

from runa.core import Message, Role, Run
from runa.runtime.provider import Provider

RUBRIC_HELPFUL = (
    "The assistant's final response directly and usefully addresses what "
    "the user asked for in the input, rather than being evasive, off-topic, "
    "or incomplete."
)
RUBRIC_FACTUAL = (
    "Every factual claim in the assistant's final response is accurate, "
    "given general knowledge and any tool results in the transcript."
)
RUBRIC_NOT_HALLUCINATE = (
    "The assistant's final response does not assert anything as fact that "
    "is unsupported by the transcript's tool results or by general "
    "knowledge; it does not invent details, sources, or outcomes."
)
RUBRIC_GOAL = (
    "The run actually accomplishes what the input asked for: any tool "
    "calls needed to satisfy the request were made and succeeded, and the "
    "final result reflects a completed goal rather than a plausible-"
    "sounding response that stops short of it."
)

_JUDGE_PROMPT = """You are grading a single AI agent run against one criterion.

Criterion: {rubric}

Transcript:
{transcript}

Reply with exactly one word on the first line, PASS or FAIL, followed by a \
one-sentence reason on the second line."""


class JudgeParseError(Exception):
    """Raised when a Judge's model response doesn't start with PASS/FAIL."""


@dataclass
class Verdict:
    passed: bool
    reasoning: str


def _format_transcript(run: Run) -> str:
    lines = [f"User input: {run.input!r}"]
    for message in run.messages:
        if message.role is Role.ASSISTANT:
            if message.content:
                lines.append(f"Assistant: {message.content}")
            for call in message.tool_calls:
                lines.append(f"Assistant called {call.name}({call.arguments!r})")
        elif message.role is Role.TOOL:
            lines.append(f"Tool result: {message.content}")
    return "\n".join(lines)


def _parse_verdict(content: str) -> Verdict:
    lines = [line.strip() for line in content.strip().splitlines() if line.strip()]
    if not lines or lines[0].upper() not in ("PASS", "FAIL"):
        raise JudgeParseError(
            f"expected PASS or FAIL on the first line, got {content!r}"
        )
    return Verdict(
        passed=lines[0].upper() == "PASS",
        reasoning=" ".join(lines[1:]) or "(no reason given)",
    )


class Judge:
    """Grades a Run's transcript against a rubric using a Provider.

    Reuses the `Provider` contract (`complete(messages=..., tools=...,
    model=...)`) that drives Agent execution, so any Provider Runa already
    knows how to talk to (Anthropic, OpenAI, a scripted test fake) works as
    a judge with no separate client. Always calls with `tools=[]`: a Judge
    never calls tools of its own, it only reasons over the transcript it's
    handed.
    """

    def __init__(self, provider: Provider, *, model: str | None = None) -> None:
        self.provider = provider
        self.model = model

    async def grade(self, run: Run, rubric: str) -> Verdict:
        prompt = _JUDGE_PROMPT.format(rubric=rubric, transcript=_format_transcript(run))
        message = await self.provider.complete(
            messages=[Message(role=Role.USER, content=prompt)],
            tools=[],
            model=self.model,
        )
        return _parse_verdict(message.content)
