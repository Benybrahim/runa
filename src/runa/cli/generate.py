"""cli/generate.py: generate scaffolding inside an existing Runa app.

Reads structure, not configuration: a new agent goes to `app/agents/`
because that's the convention `runa new` established, not because anything
is configured to say so. `tool` and `evaluation` follow the same pattern
into `app/tools/`/`app/evaluations/`.

Every template here is self-contained and immediately importable: `runa
eval`/`runa test` succeed against a freshly generated file (0 cases, an
inert stub Agent/tool) the same way they do against an empty
`app/evaluations/`/`app/tests/`, rather than crashing until the developer
fills in the TODOs.
"""

import re
from pathlib import Path

from runa.cli._project import NotARunaProject

_AGENT_TEMPLATE = '''from runa import Agent


class {class_name}(Agent):
    name = "{name}"
    instructions = """
    TODO: describe what {class_name} does.
    """
'''

_TOOL_TEMPLATE = '''from runa import tool


@tool
def {func_name}() -> str:
    """TODO: describe what this tool does."""
    raise NotImplementedError
'''

_PROMPT_TEMPLATE = """# {name}

TODO: write the prompt {name} uses.
"""

_EVALUATION_TEMPLATE = """from runa import Agent, Case

# TODO: replace with the agent you actually want to evaluate, e.g.:
# from app.agents.example_agent import ExampleAgent
# agent = ExampleAgent()


class _{class_name}Placeholder(Agent):
    name = "{class_name}Placeholder"
    instructions = "TODO: replace this with the Agent {name} should evaluate."


agent = _{class_name}Placeholder()

dataset: list[Case] = [
    # Case(
    #     input="TODO: the input to run the agent against",
    #     expected="TODO: what a good answer says",
    # ),
]
"""


class AgentAlreadyExists(Exception):
    """Raised when the target agent file already exists."""


class ToolAlreadyExists(Exception):
    """Raised when the target tool file already exists."""


class PromptAlreadyExists(Exception):
    """Raised when the target prompt file already exists."""


class EvaluationAlreadyExists(Exception):
    """Raised when the target evaluation file already exists."""


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
    """Write a new Agent subclass into `root/app/agents/`.

    `name` becomes the Python class name (suffixed with `Agent` if it isn't already). The
    class's declared `name` attribute — the identity `runa chat` looks up, and the SDK uses
    for traces/instructions/handoffs — is that class name's snake_case form (e.g.
    `support_agent`), matching the file it's written to.
    """
    agents_dir = _require_dir(root, "app", "agents")

    class_name = name if name.endswith("Agent") else f"{name}Agent"
    snake_name = _snake_case(class_name)
    agent_file = agents_dir / f"{snake_name}.py"
    if agent_file.exists():
        raise AgentAlreadyExists(f"{agent_file} already exists")

    agent_file.write_text(_AGENT_TEMPLATE.format(class_name=class_name, name=snake_name))
    return agent_file


def generate_tool(name: str, *, root: Path) -> Path:
    """Write a new `@tool`-decorated function into `root/app/tools/`."""
    tools_dir = _require_dir(root, "app", "tools")

    func_name = _snake_case(name)
    tool_file = tools_dir / f"{func_name}.py"
    if tool_file.exists():
        raise ToolAlreadyExists(f"{tool_file} already exists")

    tool_file.write_text(_TOOL_TEMPLATE.format(func_name=func_name))
    return tool_file


def generate_prompt(name: str, *, root: Path) -> Path:
    """Write a new prompt file into `root/app/prompts/`.

    Plain markdown, not Python: a prompt is text an agent's `instructions` can load, kept out
    of source the same way a query lives outside application code.
    """
    prompts_dir = _require_dir(root, "app", "prompts")

    file_stem = _snake_case(name)
    prompt_file = prompts_dir / f"{file_stem}.md"
    if prompt_file.exists():
        raise PromptAlreadyExists(f"{prompt_file} already exists")

    prompt_file.write_text(_PROMPT_TEMPLATE.format(name=file_stem))
    return prompt_file


def generate_evaluation(name: str, *, root: Path) -> Path:
    """Write a new eval dataset module into `root/app/evaluations/`.

    Unlike `generate_agent`/`generate_tool`, `name` doesn't become a class: `app/evaluations/`
    modules are plain scripts declaring module-level `agent`/`dataset` (see `cli/eval.py`), so it
    only shapes the filename and the placeholder Agent's docstring.
    """
    evaluations_dir = _require_dir(root, "app", "evaluations")

    file_stem = _snake_case(name[:-5] if name.endswith("Agent") else name)
    eval_file = evaluations_dir / f"{file_stem}_eval.py"
    if eval_file.exists():
        raise EvaluationAlreadyExists(f"{eval_file} already exists")

    placeholder_name = name[:1].upper() + name[1:]
    eval_file.write_text(_EVALUATION_TEMPLATE.format(class_name=placeholder_name, name=name))
    return eval_file
