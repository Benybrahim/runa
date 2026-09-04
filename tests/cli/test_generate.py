import pytest

from runa.cli.generate import (
    AgentAlreadyExists,
    EvaluationAlreadyExists,
    NotARunaProject,
    ToolAlreadyExists,
    generate_agent,
    generate_evaluation,
    generate_tool,
)
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


def test_generate_tool_writes_a_class_named_after_the_given_name(tmp_path):
    project_dir = scaffold_project("acme", root=tmp_path)

    tool_file = generate_tool("WebSearch", root=project_dir)

    assert tool_file == project_dir / "app" / "tools" / "web_search_tool.py"
    content = tool_file.read_text()
    assert "class WebSearchTool(Tool):" in content
    assert "from runa import Tool" in content


def test_generate_tool_does_not_double_the_tool_suffix(tmp_path):
    project_dir = scaffold_project("acme", root=tmp_path)

    tool_file = generate_tool("WebSearchTool", root=project_dir)

    assert tool_file == project_dir / "app" / "tools" / "web_search_tool.py"
    assert "class WebSearchTool(Tool):" in tool_file.read_text()


def test_generate_tool_raises_outside_a_runa_project(tmp_path):
    with pytest.raises(NotARunaProject):
        generate_tool("WebSearch", root=tmp_path)


def test_generate_tool_raises_if_the_file_already_exists(tmp_path):
    project_dir = scaffold_project("acme", root=tmp_path)
    generate_tool("WebSearch", root=project_dir)

    with pytest.raises(ToolAlreadyExists):
        generate_tool("WebSearch", root=project_dir)


def test_generate_evaluation_writes_a_self_contained_valid_module(tmp_path):
    project_dir = scaffold_project("acme", root=tmp_path)

    eval_file = generate_evaluation("Weather", root=project_dir)

    assert eval_file == project_dir / "app" / "evaluations" / "weather_eval.py"
    content = eval_file.read_text()
    assert "agent = _WeatherPlaceholder()" in content
    assert "cases: list[EvalCase] = [" in content

    # The generated module must actually import cleanly — a freshly
    # generated eval file that can't even be imported would break `runa
    # eval` immediately, before the developer has touched a single TODO.
    namespace: dict = {}
    exec(compile(content, str(eval_file), "exec"), namespace)
    assert namespace["cases"] == []
    assert namespace["agent"].instructions


def test_generate_evaluation_strips_a_trailing_agent_suffix_from_the_filename(
    tmp_path,
):
    project_dir = scaffold_project("acme", root=tmp_path)

    eval_file = generate_evaluation("WeatherAgent", root=project_dir)

    assert eval_file == project_dir / "app" / "evaluations" / "weather_eval.py"


def test_generate_evaluation_raises_outside_a_runa_project(tmp_path):
    with pytest.raises(NotARunaProject):
        generate_evaluation("Weather", root=tmp_path)


def test_generate_evaluation_raises_if_the_file_already_exists(tmp_path):
    project_dir = scaffold_project("acme", root=tmp_path)
    generate_evaluation("Weather", root=project_dir)

    with pytest.raises(EvaluationAlreadyExists):
        generate_evaluation("Weather", root=project_dir)
