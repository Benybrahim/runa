"""Tests for `runa.cli.generate`: `generate_agent`/`generate_tool`/`generate_evaluation`."""

from pathlib import Path

import pytest

from runa.cli._project import NotARunaProject
from runa.cli.generate import (
    AgentAlreadyExists,
    EvaluationAlreadyExists,
    ToolAlreadyExists,
    generate_agent,
    generate_evaluation,
    generate_tool,
)
from runa.cli.new import scaffold_project


def test_generate_agent_writes_a_runa_agent_subclass(tmp_path: Path) -> None:
    """`generate_agent` writes a class named `{name}Agent` under `app/agents/`."""
    project_dir = scaffold_project("demo", root=tmp_path)

    agent_file = generate_agent("Support", root=project_dir)

    assert agent_file == project_dir / "app" / "agents" / "support_agent.py"
    content = agent_file.read_text()
    assert "class SupportAgent(Agent):" in content
    assert 'name = "support_agent"' in content


def test_generate_agent_does_not_double_append_agent_suffix(tmp_path: Path) -> None:
    """Passing a name already ending in `Agent` doesn't produce `SupportAgentAgent`."""
    project_dir = scaffold_project("demo", root=tmp_path)

    agent_file = generate_agent("SupportAgent", root=project_dir)

    assert "class SupportAgent(Agent):" in agent_file.read_text()


def test_generate_agent_raises_if_the_file_already_exists(tmp_path: Path) -> None:
    """`generate_agent` refuses to overwrite an existing agent file."""
    project_dir = scaffold_project("demo", root=tmp_path)
    generate_agent("Support", root=project_dir)

    with pytest.raises(AgentAlreadyExists):
        generate_agent("Support", root=project_dir)


def test_generate_agent_raises_outside_a_runa_project(tmp_path: Path) -> None:
    """`generate_agent` refuses to run where `app/agents/` doesn't exist."""
    with pytest.raises(NotARunaProject):
        generate_agent("Support", root=tmp_path)


def test_generate_tool_writes_a_snake_case_tool_function(tmp_path: Path) -> None:
    """`generate_tool` writes an `@tool`-decorated function, not a `Tool` subclass."""
    project_dir = scaffold_project("demo", root=tmp_path)

    tool_file = generate_tool("SendEmail", root=project_dir)

    assert tool_file == project_dir / "app" / "tools" / "send_email.py"
    content = tool_file.read_text()
    assert "@tool" in content
    assert "def send_email() -> str:" in content


def test_generate_tool_raises_if_the_file_already_exists(tmp_path: Path) -> None:
    """`generate_tool` refuses to overwrite an existing tool file."""
    project_dir = scaffold_project("demo", root=tmp_path)
    generate_tool("search", root=project_dir)

    with pytest.raises(ToolAlreadyExists):
        generate_tool("search", root=project_dir)


def test_generate_evaluation_writes_a_module_declaring_agent_and_dataset(tmp_path: Path) -> None:
    """`generate_evaluation` writes a placeholder Agent plus an empty `dataset` list."""
    project_dir = scaffold_project("demo", root=tmp_path)

    eval_file = generate_evaluation("Support", root=project_dir)

    assert eval_file == project_dir / "app" / "evaluations" / "support_eval.py"
    content = eval_file.read_text()
    assert "agent = _SupportPlaceholder()" in content
    assert "dataset: list[Case] = [" in content


def test_generate_evaluation_raises_if_the_file_already_exists(tmp_path: Path) -> None:
    """`generate_evaluation` refuses to overwrite an existing evaluation module."""
    project_dir = scaffold_project("demo", root=tmp_path)
    generate_evaluation("Support", root=project_dir)

    with pytest.raises(EvaluationAlreadyExists):
        generate_evaluation("Support", root=project_dir)
