# CodeAgent

A worked example touching every primitive Runa gives you, in order: agent,
[tool](tools.md), [guardrail](guardrails.md) on the agent's input/output,
delegation and handoffs (see [Subagents](subagents.md)), guardrail on a
tool, [approval](approval.md) on a tool (both boolean and predicate
forms), context — [session](sessions.md), [memory](memory.md),
[knowledge](memory.md) — [MCP](mcp.md), [tracing](tracing.md), and
[evaluation](evaluation.md).

It's a toy version of the kind of agent behind tools like Claude Code or
Cursor, built up one primitive at a time so each stays in focus. The full
listing is at the bottom of each stage.

## Agent

```python
from runa import Agent


class CodingAgent(Agent):
    name = "coding_agent"
    instructions = "You write and edit code for the user, one file at a time."
```

## Tool

A tool is a plain function. To keep this stage simple, `read_file` and
`write_file` stand in for a real file with a single module-level
variable:

```python
from runa import tool

_buffer = ""  # stands in for "the open file"


@tool
def read_file() -> str:
    """Return the current contents of the open file."""
    return _buffer


@tool
def write_file(content: str) -> str:
    """Replace the open file's contents."""
    global _buffer
    _buffer = content
    return f"Wrote {len(content)} characters."


class CodeAgent(Agent):
    name = "code_agent"
    instructions = "You write and edit code for the user, one file at a time."
    tools = [read_file, write_file]
```

## Guardrail on Agent Input/Output

A guardrail is a predicate that trips the run when it returns `True`.
Bound to `.input` it sees the user's message; bound to `.output` it sees
the agent's final reply.

```python
from runa import guardrail


@guardrail
def block_empty(input: str) -> bool:
    """Trip when the user sends an empty message."""
    return not input.strip()


@guardrail
def blocks_leaked_secret(output: str) -> bool:
    """Trip if the reply looks like it contains an API key."""
    return "sk-" in output


class CodeAgent(Agent):
    name = "code_agent"
    instructions = "You write and edit code for the user, one file at a time."
    tools = [read_file, write_file]
    guardrails = [block_empty.input, blocks_leaked_secret.output]
```

## Delegation and Handoffs

For a second opinion before writing, `CodeAgent` delegates to a
`ReviewerAgent` — it stays in control and gets the review back, like a
tool call. For anything beyond editing the open file, it hands off to a
`SeniorEngineerAgent`, which takes over the conversation entirely.

```python
class ReviewerAgent(Agent):
    name = "reviewer_agent"
    instructions = "You review a code change and point out any issues, briefly."


class SeniorEngineerAgent(Agent):
    name = "senior_engineer_agent"
    instructions = "You take over for architecture-level questions the coach can't answer."


class CodeAgent(Agent):
    name = "code_agent"
    instructions = "You write and edit code for the user, one file at a time."
    tools = [read_file, write_file]
    guardrails = [block_empty.input, blocks_leaked_secret.output]
    subagents = [ReviewerAgent.delegate, SeniorEngineerAgent.handoff]
```

## Guardrail on a Tool

The same `@guardrail` predicate works against a tool's arguments. On a
tool, `.input` sees the call's parsed arguments as a `dict`.

```python
@guardrail
def blocks_dangerous_command(args: dict) -> bool:
    """Trip if the written content contains a destructive shell command."""
    return "rm -rf" in args.get("content", "")


@tool(guardrails=[blocks_dangerous_command.input])
def write_file(content: str) -> str:
    """Replace the open file's contents."""
    global _buffer
    _buffer = content
    return f"Wrote {len(content)} characters."
```

## Approval on a Tool

`needs_approval` pauses a tool call for a human to sign off, instead of
deciding the outcome itself like a guardrail does. It takes either a
plain boolean or a predicate function.

Deleting the file is irreversible no matter what — always ask:

```python
@tool(needs_approval=True)
def delete_file() -> str:
    """Clear the open file's contents."""
    global _buffer
    _buffer = ""
    return "File cleared."
```

A large rewrite is only worth a second look past a size threshold — ask
with a predicate instead. Its parameters are looked up by name from the
tool's parsed arguments:

```python
from runa import approval


@approval
def is_large_change(content: str) -> bool:
    """Rewrites of 500+ characters need a human to confirm."""
    return len(content) >= 500


@tool(guardrails=[blocks_dangerous_command.input], needs_approval=is_large_change)
def write_file(content: str) -> str:
    """Replace the open file's contents."""
    global _buffer
    _buffer = content
    return f"Wrote {len(content)} characters."


class CodeAgent(Agent):
    name = "code_agent"
    instructions = "You write and edit code for the user, one file at a time."
    tools = [read_file, write_file, delete_file]
    guardrails = [block_empty.input, blocks_leaked_secret.output]
    subagents = [ReviewerAgent.delegate, SeniorEngineerAgent.handoff]
```

## Context

The module-level `_buffer` has a problem: every user of `CodeAgent`
shares the same "file," and two runs at once stomp on each other.
`context` fixes that — it's per-run data, never sent to the model, but
plumbed through to `instructions` and tools as-is. A parameter named
`ctx` on a tool receives it instead of a model-supplied argument.

```python
from dataclasses import dataclass


@dataclass
class CodeContext:
    filename: str
    buffer: str = ""


def instructions(context: CodeContext) -> str:
    return f"You write and edit {context.filename} for the user, one change at a time."


@tool
def read_file(ctx) -> str:
    """Return the current contents of the open file."""
    return ctx.context.buffer


@tool(guardrails=[blocks_dangerous_command.input], needs_approval=is_large_change)
def write_file(ctx, content: str) -> str:
    """Replace the open file's contents."""
    ctx.context.buffer = content
    return f"Wrote {len(content)} characters."


@tool(needs_approval=True)
def delete_file(ctx) -> str:
    """Clear the open file's contents."""
    ctx.context.buffer = ""
    return "File cleared."
```

That covers *this run's* file. Two more kinds of context live longer:

* **Session** persists conversation history across processes, keyed by an
  id you choose:

  ```python
  from runa import SQLiteSession

  session = SQLiteSession("project-123")
  agent.run_sync("Add a docstring.", context=CodeContext(...), session=session)
  ```

* **Memory** (`memory = "auto"`) remembers durable facts about a user
  across conversations — a preferred code style, a naming convention.
* **Knowledge** (`knowledge = "auto"`) retrieves from `app/knowledge/` —
  the project's own style guide or architecture docs — before each turn.

```python
class CodeAgent(Agent):
    name = "code_agent"
    instructions = instructions
    tools = [read_file, write_file, delete_file]
    guardrails = [block_empty.input, blocks_leaked_secret.output]
    subagents = [ReviewerAgent.delegate, SeniorEngineerAgent.handoff]
    memory = "auto"
    knowledge = "auto"
```

## MCP

The toy `_buffer` tools stand in for a real filesystem. Swap them for an
[MCP](https://modelcontextprotocol.io) server and `CodeAgent` gets real
file access, with no change to guardrails or approvals — MCP tools go
through the same `needs_approval` gate as any other tool:

```python
from runa import MCPServer

files = MCPServer(name="files").stdio("npx", ["-y", "@modelcontextprotocol/server-filesystem", "."])


class CodeAgent(Agent):
    name = "code_agent"
    instructions = instructions
    mcp = [files]
    guardrails = [block_empty.input, blocks_leaked_secret.output]
    subagents = [ReviewerAgent.delegate, SeniorEngineerAgent.handoff]
    memory = "auto"
    knowledge = "auto"
```

## Tracing

Every run is traced automatically — no setup step:

```python
run = agent.run_sync("Add a docstring.", context=CodeContext(filename="app.py"))
print(run.trace)  # the span tree: agent, LLM call, tool calls, guardrails
```

```bash
runa traces list
runa traces errors
runa traces show TRACE_ID
```

## Evaluation

`runa generate evaluation CodeAgent` scaffolds a dataset graded against
the agent, not just a single `assert`:

```python
# app/evaluations/code_agent_eval.py
from runa import Case

from app.agents.code_agent import CodeAgent

agent = CodeAgent()

dataset = [
    Case(
        input="Add a docstring to this function.",
        expected="Writes a docstring without changing behavior",
        expected_tool="write_file",
    ),
]
```

```bash
runa eval
```

## Run It

```python
from app.agents.code_agent import CodeAgent, CodeContext

agent = CodeAgent()
run = agent.run_sync(
    "Add a docstring to this file.",
    context=CodeContext(filename="app.py", buffer="def main():\n    pass\n"),
)
print(run.output)
```

Or talk to it directly:

```bash
runa chat code_agent
```
