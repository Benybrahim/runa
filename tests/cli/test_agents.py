"""Tests for `runa.cli.agents`: `list_agents`."""

from pathlib import Path

import pytest

from runa.cli._project import NotARunaProject
from runa.cli.agents import list_agents
from runa.cli.generate import generate_agent
from runa.cli.new import scaffold_project


def test_list_agents_finds_every_declared_agent(tmp_path: Path) -> None:
    """`list_agents` returns one `AgentInfo` per Agent subclass under `app/agents/`."""
    project_dir = scaffold_project("demo", root=tmp_path)
    generate_agent("SupportAgent", root=project_dir)

    infos = list_agents(root=project_dir)

    assert [info.name for info in infos] == ["support_agent"]
    assert infos[0].class_name == "SupportAgent"


def test_list_agents_reports_defaults_for_a_bare_agent(tmp_path: Path) -> None:
    """A freshly generated Agent has no tools/guardrails/subagents and memory/knowledge off."""
    project_dir = scaffold_project("demo", root=tmp_path)
    generate_agent("SupportAgent", root=project_dir)

    info = list_agents(root=project_dir)[0]

    assert info.tools == []
    assert info.guardrails == []
    assert info.subagents == []
    assert info.memory == "off"
    assert info.knowledge == "off"


def test_list_agents_returns_empty_list_when_no_agents_declared(tmp_path: Path) -> None:
    """`list_agents` returns `[]`, not an error, for a project with no Agent subclasses yet."""
    project_dir = scaffold_project("demo", root=tmp_path)

    assert list_agents(root=project_dir) == []


def test_list_agents_raises_outside_a_runa_project(tmp_path: Path) -> None:
    """`list_agents` raises `NotARunaProject` when `root` has no `app/agents/` directory."""
    with pytest.raises(NotARunaProject):
        list_agents(root=tmp_path)
