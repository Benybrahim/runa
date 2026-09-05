"""cli/generate.py: generate scaffolding inside an existing Runa app.

Reads structure, not configuration: a new agent goes to `app/agents/`
because that's the convention `runa new` established, not because
anything was configured to say so (manifesto §2). `tool` and `evaluation`
follow the same pattern into `app/tools/`/`app/evaluations/`, the two
generators "natural next generators in the same
spirit" alongside `agent`.

Every template here is self-contained and immediately importable:
`runa eval`/`runa test` succeed against a freshly generated file (0/0
cases, an inert stub Agent/Tool) the same way they do against an empty
`app/evaluations/`/`app/tests/`, rather than crashing until the developer
fills in the TODOs. `generate_evaluation` in particular embeds its own
placeholder Agent instead of importing one from `app/agents/`, so it never
depends on a specific agent file already existing.
"""

import re
from pathlib import Path

_AGENT_TEMPLATE = '''from runa import Agent


class {class_name}(Agent):
    instructions = """
    TODO: describe what {class_name} does.
    """
    tools = []
'''

_TOOL_TEMPLATE = '''from runa import Tool


class {class_name}(Tool):
    """TODO: describe what {class_name} does."""

    def call(self) -> str:
        raise NotImplementedError
'''

_EVALUATION_TEMPLATE = """from runa import Agent, EvalCase, expect

# TODO: replace with the agent you actually want to evaluate, e.g.:
# from app.agents.example_agent import ExampleAgent
# agent = ExampleAgent()


class _{class_name}Placeholder(Agent):
    instructions = "TODO: replace this with the Agent {name} should evaluate."


agent = _{class_name}Placeholder()

cases: list[EvalCase] = [
    # EvalCase(
    #     name="TODO: name this case",
    #     input="TODO: the input to run the agent against",
    #     check=lambda run: expect(run).to_be_completed(),
    # ),
]
"""


class AgentAlreadyExists(Exception):
    """Raised when the target agent file already exists."""


class ToolAlreadyExists(Exception):
    """Raised when the target tool file already exists."""


class EvaluationAlreadyExists(Exception):
    """Raised when the target evaluation file already exists."""


class NotARunaProject(Exception):
    """Raised when the expected `app/` subdirectory isn't present under `root`."""


def _snake_case(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def _require_dir(root: Path, *parts: str) -> Path:
    target_dir = root.joinpath(*parts)
    if not target_dir.is_dir():
        raise NotARunaProject(
            f"{target_dir} does not exist, run this from inside a Runa "
            "project created with `runa new`"
        )
    return target_dir


def generate_agent(name: str, *, root: Path) -> Path:
    """Write a new Agent subclass into `root/app/agents/`."""
    agents_dir = _require_dir(root, "app", "agents")

    class_name = name if name.endswith("Agent") else f"{name}Agent"
    agent_file = agents_dir / f"{_snake_case(class_name)}.py"
    if agent_file.exists():
        raise AgentAlreadyExists(f"{agent_file} already exists")

    agent_file.write_text(_AGENT_TEMPLATE.format(class_name=class_name))
    return agent_file


def generate_tool(name: str, *, root: Path) -> Path:
    """Write a new Tool subclass into `root/app/tools/`."""
    tools_dir = _require_dir(root, "app", "tools")

    class_name = name if name.endswith("Tool") else f"{name}Tool"
    tool_file = tools_dir / f"{_snake_case(class_name)}.py"
    if tool_file.exists():
        raise ToolAlreadyExists(f"{tool_file} already exists")

    tool_file.write_text(_TOOL_TEMPLATE.format(class_name=class_name))
    return tool_file


def generate_evaluation(name: str, *, root: Path) -> Path:
    """Write a new eval case module into `root/app/evaluations/`.

    Unlike `generate_agent`/`generate_tool`, `name` doesn't become a class:
    `app/evaluations/` modules are plain scripts declaring module-level
    `agent`/`cases` (see `cli/eval.py`), so it only shapes the filename and
    the placeholder Agent's docstring.
    """
    evaluations_dir = _require_dir(root, "app", "evaluations")

    file_stem = _snake_case(name if not name.endswith("Agent") else name[:-5])
    eval_file = evaluations_dir / f"{file_stem}_eval.py"
    if eval_file.exists():
        raise EvaluationAlreadyExists(f"{eval_file} already exists")

    placeholder_name = name[:1].upper() + name[1:]
    eval_file.write_text(
        _EVALUATION_TEMPLATE.format(class_name=placeholder_name, name=name)
    )
    return eval_file
