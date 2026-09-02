"""cli/generate.py: generate scaffolding inside an existing Runa app.

Reads structure, not configuration: a new agent goes to `app/agents/`
because that's the convention `runa new` established, not because
anything was configured to say so (manifesto §2).
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


class AgentAlreadyExists(Exception):
    """Raised when the target agent file already exists."""


class NotARunaProject(Exception):
    """Raised when `app/agents/` isn't present under `root`."""


def _snake_case(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def generate_agent(name: str, *, root: Path) -> Path:
    """Write a new Agent subclass into `root/app/agents/`."""
    agents_dir = root / "app" / "agents"
    if not agents_dir.is_dir():
        raise NotARunaProject(
            f"{agents_dir} does not exist — run this from inside a Runa "
            "project created with `runa new`"
        )

    class_name = name if name.endswith("Agent") else f"{name}Agent"
    agent_file = agents_dir / f"{_snake_case(class_name)}.py"
    if agent_file.exists():
        raise AgentAlreadyExists(f"{agent_file} already exists")

    agent_file.write_text(_AGENT_TEMPLATE.format(class_name=class_name))
    return agent_file
