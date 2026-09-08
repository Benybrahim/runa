"""Tests for `runa.eval.judge`: the judge model semantic metrics grade with."""

import asyncio
from typing import Any

import pytest

from runa.eval.judge import extract_json, judge_model


def test_judge_model_asks_through_the_named_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """`judge_model(...).ask(...)` runs the prompt through an SDK Agent using that model."""
    captured: dict[str, Any] = {}

    async def fake_run(agent: Any, input: Any, **kwargs: Any) -> Any:
        captured["model"] = agent.model
        captured["input"] = input

        class _Result:
            final_output = "PASS"

        return _Result()

    monkeypatch.setattr("runa.eval.judge.Runner.run", staticmethod(fake_run))

    output = asyncio.run(judge_model("gpt-5.4-nano").ask("grade this"))

    assert output == "PASS"
    assert captured["model"] == "gpt-5.4-nano"
    assert captured["input"] == "grade this"


def test_extract_json_parses_a_clean_object() -> None:
    """A reply that's already valid JSON parses straight through."""
    assert extract_json('{"score": 0.8}') == {"score": 0.8}


def test_extract_json_ignores_surrounding_prose() -> None:
    """A judge that wraps its JSON in commentary or markdown fences still parses."""
    reply = 'Sure, here is my verdict:\n```json\n{"verdict": "yes", "reason": "matches"}\n```'
    assert extract_json(reply) == {"verdict": "yes", "reason": "matches"}


def test_extract_json_repairs_a_trailing_comma() -> None:
    """A trailing comma before a closing bracket is stripped and retried, not just rejected."""
    reply = '{"statements": ["a", "b",], "extra": "x",}'
    assert extract_json(reply) == {"statements": ["a", "b"], "extra": "x"}


def test_extract_json_raises_when_no_object_is_present() -> None:
    """A reply with no `{...}` at all raises rather than silently returning garbage."""
    with pytest.raises(ValueError):
        extract_json("no json here")


def test_extract_json_raises_on_unrepairable_json() -> None:
    """Malformed JSON that isn't just a trailing comma still raises."""
    with pytest.raises(ValueError):
        extract_json('{"score": }')
