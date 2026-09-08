"""Tests for `runa.cli.run`: `find_agent_class`/`run_agent`/`run_agent_repl`."""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from agents.items import ToolApprovalItem
from openai.types.responses import ResponseFunctionToolCall

from runa.agent import Agent
from runa.cli import _approvals
from runa.cli._project import NotARunaProject, loaded_app
from runa.cli.new import scaffold_project
from runa.cli.run import AgentNotFound, find_agent_class, run_agent, run_agent_repl


def _write_agent(project_dir: Path, filename: str, source: str) -> None:
    (project_dir / "app" / "agents" / filename).write_text(source)


def test_find_agent_class_matches_the_exact_class_name(tmp_path: Path) -> None:
    """`find_agent_class` finds an Agent subclass by its exact class name."""
    project_dir = scaffold_project("demo", root=tmp_path)
    _write_agent(
        project_dir,
        "support_agent.py",
        "from runa import Agent\n\n\nclass Support(Agent):\n    name = 'Support'\n",
    )

    with loaded_app(project_dir):
        agent_cls = find_agent_class("Support", agents_dir=project_dir / "app" / "agents")

    assert agent_cls.__name__ == "Support"


def test_find_agent_class_appends_the_agent_suffix(tmp_path: Path) -> None:
    """`find_agent_class` finds `SupportAgent` when asked for plain `Support`."""
    project_dir = scaffold_project("demo", root=tmp_path)
    _write_agent(
        project_dir,
        "support_agent.py",
        "from runa import Agent\n\n\nclass SupportAgent(Agent):\n    name = 'SupportAgent'\n",
    )

    with loaded_app(project_dir):
        agent_cls = find_agent_class("Support", agents_dir=project_dir / "app" / "agents")

    assert agent_cls.__name__ == "SupportAgent"


def test_find_agent_class_raises_when_nothing_matches(tmp_path: Path) -> None:
    """`find_agent_class` raises `AgentNotFound` when no Agent subclass matches."""
    project_dir = scaffold_project("demo", root=tmp_path)

    with pytest.raises(AgentNotFound):
        find_agent_class("Nope", agents_dir=project_dir / "app" / "agents")


def test_run_agent_raises_outside_a_runa_project(tmp_path: Path) -> None:
    """`run_agent` refuses to run where `app/agents/` doesn't exist."""
    with pytest.raises(NotARunaProject):
        run_agent("Support", "hi", root=tmp_path)


@dataclass
class _FakeState:
    """A stand-in for `RunState`, just enough for `run_agent` to serialize."""

    payload: dict[str, Any] = field(default_factory=lambda: {"fake": "state"})

    def to_json(self) -> dict[str, Any]:
        """Return the fixed payload `run_agent` will `json.dumps()`."""
        return self.payload


@dataclass
class _FakeResult:
    """A stand-in for `RunResult`, just enough for `run_agent` to consume."""

    final_output: Any = "the answer"
    interruptions: list[Any] = field(default_factory=list)

    def to_state(self) -> _FakeState:
        """Return a fake state, mirroring `RunResult.to_state()`."""
        return _FakeState()


def _scaffold_with_agent(tmp_path: Path) -> Path:
    project_dir = scaffold_project("demo", root=tmp_path)
    _write_agent(
        project_dir,
        "support_agent.py",
        "from runa import Agent\n\n\nclass SupportAgent(Agent):\n    name = 'SupportAgent'\n",
    )
    return project_dir


def test_run_agent_returns_the_final_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`run_agent` returns `result.final_output` when the run completes cleanly."""
    project_dir = _scaffold_with_agent(tmp_path)

    def fake_run_sync(agent: Any, message: Any, **kwargs: Any) -> _FakeResult:
        return _FakeResult(final_output="hello!")

    monkeypatch.setattr("runa.cli.run.Runner.run_sync", staticmethod(fake_run_sync))

    assert run_agent("Support", "hi", root=project_dir) == "hello!"


def test_run_agent_sessions_by_the_agent_class_name_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no explicit `session_id`, `run_agent` keys the session by the Agent's class name."""
    project_dir = _scaffold_with_agent(tmp_path)
    captured: dict[str, Any] = {}

    def fake_run_sync(agent: Any, message: Any, *, session: Any, **kwargs: Any) -> _FakeResult:
        captured["session_id"] = session.session_id
        return _FakeResult()

    monkeypatch.setattr("runa.cli.run.Runner.run_sync", staticmethod(fake_run_sync))

    run_agent("Support", "hi", root=project_dir)

    assert captured["session_id"] == "SupportAgent"


def test_run_agent_honors_an_explicit_session_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An explicit `session_id` overrides the default class-name session."""
    project_dir = _scaffold_with_agent(tmp_path)
    captured: dict[str, Any] = {}

    def fake_run_sync(agent: Any, message: Any, *, session: Any, **kwargs: Any) -> _FakeResult:
        captured["session_id"] = session.session_id
        return _FakeResult()

    monkeypatch.setattr("runa.cli.run.Runner.run_sync", staticmethod(fake_run_sync))

    run_agent("Support", "hi", root=project_dir, session_id="ticket-42")

    assert captured["session_id"] == "ticket-42"


def test_run_agent_saves_a_pending_approval_when_interrupted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A run that pauses for approval is saved to `runa.db` instead of returning a final answer."""
    project_dir = _scaffold_with_agent(tmp_path)
    agent = Agent(name="SupportAgent")
    interruption = ToolApprovalItem(
        agent=agent,
        raw_item=ResponseFunctionToolCall(
            call_id="call_1", name="delete_file", arguments="{}", type="function_call"
        ),
    )

    def fake_run_sync(agent: Any, message: Any, **kwargs: Any) -> _FakeResult:
        return _FakeResult(interruptions=[interruption])

    monkeypatch.setattr("runa.cli.run.Runner.run_sync", staticmethod(fake_run_sync))

    output = run_agent("Support", "delete it", root=project_dir)

    assert "awaiting approval" in output
    assert "delete_file" in output
    assert "call_1" in output
    pending = _approvals.get_pending(
        project_dir / "runa.db", session_id="SupportAgent", tool_call_id="call_1"
    )
    assert pending is not None
    assert pending.tool_name == "delete_file"
    assert json.loads(pending.state_json) == {"fake": "state"}


def _feed_input(monkeypatch: pytest.MonkeyPatch, lines: list[str]) -> None:
    """Make `input()` return each of `lines` in turn, then raise `EOFError`."""
    remaining = iter(lines)

    def fake_input(prompt: str = "") -> str:
        try:
            return next(remaining)
        except StopIteration:
            raise EOFError from None

    monkeypatch.setattr("builtins.input", fake_input)


def test_run_agent_repl_sends_each_line_and_prints_the_reply(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Each REPL line becomes a turn, and its final output is printed before the next prompt."""
    project_dir = _scaffold_with_agent(tmp_path)
    _feed_input(monkeypatch, ["hi", "how are you"])
    replies = iter(["hello!", "doing fine"])

    def fake_run_sync(agent: Any, message: Any, **kwargs: Any) -> _FakeResult:
        return _FakeResult(final_output=next(replies))

    monkeypatch.setattr("runa.cli.run.Runner.run_sync", staticmethod(fake_run_sync))

    run_agent_repl("Support", root=project_dir)

    out = capsys.readouterr().out
    assert "hello!" in out
    assert "doing fine" in out


def test_run_agent_repl_exits_on_the_exit_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Typing `exit` ends the loop without calling the Runner."""
    project_dir = _scaffold_with_agent(tmp_path)
    _feed_input(monkeypatch, ["exit"])
    calls: list[Any] = []

    def fake_run_sync(agent: Any, message: Any, **kwargs: Any) -> _FakeResult:
        calls.append(message)
        return _FakeResult()

    monkeypatch.setattr("runa.cli.run.Runner.run_sync", staticmethod(fake_run_sync))

    run_agent_repl("Support", root=project_dir)

    assert calls == []


@dataclass
class _FakeApprovalState:
    """A stand-in for `RunState`, recording `approve`/`reject` calls."""

    approved: list[Any] = field(default_factory=list)
    rejected: list[Any] = field(default_factory=list)

    def approve(self, item: Any) -> None:
        """Record `item` as approved, mirroring `RunState.approve()`."""
        self.approved.append(item)

    def reject(self, item: Any) -> None:
        """Record `item` as rejected, mirroring `RunState.reject()`."""
        self.rejected.append(item)


def test_run_agent_repl_approves_a_pending_tool_call_when_the_operator_says_yes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Answering `y` to the approval prompt resumes the run with the item approved."""
    project_dir = _scaffold_with_agent(tmp_path)
    agent = Agent(name="SupportAgent")
    interruption = ToolApprovalItem(
        agent=agent,
        raw_item=ResponseFunctionToolCall(
            call_id="call_1", name="delete_file", arguments="{}", type="function_call"
        ),
    )
    _feed_input(monkeypatch, ["delete it", "y"])
    state = _FakeApprovalState()

    @dataclass
    class _InterruptedResult:
        final_output: Any = None
        interruptions: list[Any] = field(default_factory=list)

        def to_state(self) -> _FakeApprovalState:
            return state

    results = iter(
        [_InterruptedResult(interruptions=[interruption]), _InterruptedResult(final_output="done")]
    )

    def fake_run_sync(agent: Any, message: Any, **kwargs: Any) -> Any:
        return next(results)

    monkeypatch.setattr("runa.cli.run.Runner.run_sync", staticmethod(fake_run_sync))

    run_agent_repl("Support", root=project_dir)

    assert state.approved == [interruption]
    assert state.rejected == []


def test_run_agent_repl_rejects_a_pending_tool_call_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Any answer other than `y` rejects the tool call rather than approving it."""
    project_dir = _scaffold_with_agent(tmp_path)
    agent = Agent(name="SupportAgent")
    interruption = ToolApprovalItem(
        agent=agent,
        raw_item=ResponseFunctionToolCall(
            call_id="call_1", name="delete_file", arguments="{}", type="function_call"
        ),
    )
    _feed_input(monkeypatch, ["delete it", "n"])
    state = _FakeApprovalState()

    @dataclass
    class _InterruptedResult:
        final_output: Any = None
        interruptions: list[Any] = field(default_factory=list)

        def to_state(self) -> _FakeApprovalState:
            return state

    results = iter(
        [_InterruptedResult(interruptions=[interruption]), _InterruptedResult(final_output="done")]
    )

    def fake_run_sync(agent: Any, message: Any, **kwargs: Any) -> Any:
        return next(results)

    monkeypatch.setattr("runa.cli.run.Runner.run_sync", staticmethod(fake_run_sync))

    run_agent_repl("Support", root=project_dir)

    assert state.rejected == [interruption]
    assert state.approved == []
