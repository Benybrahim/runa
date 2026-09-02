import pytest

from runa.cli.generate import AgentAlreadyExists, NotARunaProject, generate_agent
from runa.cli.new import scaffold_project


def test_generate_agent_writes_a_class_named_after_the_given_name(tmp_path):
    project_dir = scaffold_project("acme", root=tmp_path)

    agent_file = generate_agent("Support", root=project_dir)

    assert agent_file == project_dir / "app" / "agents" / "support_agent.py"
    content = agent_file.read_text()
    assert "class SupportAgent(Agent):" in content
    assert "from runa import Agent" in content


def test_generate_agent_does_not_double_the_agent_suffix(tmp_path):
    project_dir = scaffold_project("acme", root=tmp_path)

    agent_file = generate_agent("TriageAgent", root=project_dir)

    assert agent_file == project_dir / "app" / "agents" / "triage_agent.py"
    assert "class TriageAgent(Agent):" in agent_file.read_text()


def test_generate_agent_raises_outside_a_runa_project(tmp_path):
    with pytest.raises(NotARunaProject):
        generate_agent("Support", root=tmp_path)


def test_generate_agent_raises_if_the_file_already_exists(tmp_path):
    project_dir = scaffold_project("acme", root=tmp_path)
    generate_agent("Support", root=project_dir)

    with pytest.raises(AgentAlreadyExists):
        generate_agent("Support", root=project_dir)
