# Getting Started with Runa

This guide covers everything you need to build your first Runa agent. After
reading it, you'll know how to:

* Create a new Runa application
* Write an Agent, give it tools, and run it
* Add guardrails
* Delegate work to other agents
* Chat with your agent and persist conversations
* Test and evaluate your agent

## Guide Assumptions

This guide is for beginners who want to build their first Runa application.
It assumes no prior experience with Runa. Some familiarity with Python
helps.

## What Is Runa?

Runa is an opinionated framework for agentic AI. "Opinionated" means Runa
assumes there's a best way to build an agent application, and it's designed
to encourage that way — chiefly, through convention over configuration.

An Agent is a Python class. Its attributes — `name`, `instructions`,
`tools`, `subagents`, `guardrails` — are the whole configuration surface.
There's no separate config file, no client to instantiate, no provider to
wire up: the model string on the class (`"gpt-5.4-nano"`, `"claude-..."`,
`"gemini-..."`) tells Runa which provider to call.

## Creating a New Runa Application

### Installing Runa

Runa needs Python 3.14. Install it with [uv](https://docs.astral.sh/uv/):

```bash
uv venv --python 3.14
source .venv/bin/activate
uv add git+https://github.com/benybrahim/runa.git
```

Confirm it installed:

```bash
runa --help
```

### Creating the Application

`runa new` scaffolds a new application with everything you need:

```bash
runa new blog
cd blog
```

Take a look at what was generated:

```
blog/
├── app/
│   ├── agents/          # Agent subclasses
│   ├── tools/           # @tool-decorated functions
│   ├── prompts/         # prompt text, kept out of Python source
│   └── evaluations/     # eval cases, run with `runa eval`
├── tests/                # deterministic tests, run with `runa test`
├── config/               # shared config (clients, settings)
├── db/                   # runa.db: conversation history and traces
├── main.py               # application entry point, loads .env
├── .env                  # your model's API key — fill this in, never commit it
└── pyproject.toml
```

Open `.env` and set the API key for whichever model your agents will use:

```
OPENAI_API_KEY=sk-...
```

That's the only configuration step. Nothing else needs to be wired up
globally — a model is a per-`Agent` attribute, and Runa resolves it to the
right provider by name.

## Hello, Runa!

Let's generate an agent:

```bash
runa generate agent Greeter
```

This creates `app/agents/greeter_agent.py`:

```python
from runa import Agent


class GreeterAgent(Agent):
    name = "greeter_agent"
    instructions = """
    TODO: describe what GreeterAgent does.
    """
```

Replace the instructions:

```python
from runa import Agent


class GreeterAgent(Agent):
    name = "greeter_agent"
    instructions = "You greet the user warmly, in one sentence."
```

Run it from `main.py`, or straight from a Python shell:

```python
from app.agents.greeter_agent import GreeterAgent

agent = GreeterAgent()
run = agent.run_sync("Hi, I'm new here.")
print(run.output)
```

Or skip writing any code and talk to it directly:

```bash
runa chat greeter_agent
```

`run_sync` returns a `Run` with `.output`, `.usage`, `.status`, and
`.error`. Calling `run_sync`/`run` again on the same agent instance
continues the same conversation — `self.history` remembers what was said.

## Giving Your Agent Tools

A tool is a plain Python function. Its signature *is* its schema — Runa
reads the type hints and the docstring, so there's nothing else to declare.

```bash
runa generate tool CurrentTime
```

```python
# app/tools/current_time.py
from datetime import datetime

from runa import tool


@tool
def current_time() -> str:
    """Return the current local time as an ISO 8601 string."""
    return datetime.now().isoformat()
```

Attach it to an agent with `tools`:

```python
from runa import Agent

from app.tools.current_time import current_time


class GreeterAgent(Agent):
    name = "greeter_agent"
    instructions = "You greet the user warmly, and tell them the time if asked."
    tools = [current_time]
```

The model decides on its own when to call `current_time` — you never call
it yourself.

Omit `instructions` and it's loaded automatically from
`app/prompts/greeter_agent.md` (matching the `name`); if that file doesn't
exist yet, it's created with a `TODO` stub — the same one `runa generate
prompt` writes — ready for you to fill in:

```python
class GreeterAgent(Agent):
    name = "greeter_agent"
    tools = [current_time]
```

## Adding Guardrails

A guardrail is a predicate: `(value) -> bool`, tripping the run when it
returns `True`. Bind it to `.input` or `.output` to say which side it
checks.

```python
from runa import Agent, guardrail

from app.tools.current_time import current_time


@guardrail
def block_empty(input: str) -> bool:
    """Trip when the user sends an empty message."""
    return not input.strip()


class GreeterAgent(Agent):
    name = "greeter_agent"
    instructions = "You greet the user warmly, and tell them the time if asked."
    tools = [current_time]
    guardrails = [block_empty.input]
```

The same `@guardrail` predicate works on a tool's arguments or return
value, via `@tool(guardrails=[...])`:

```python
@guardrail
def no_args(args: dict) -> bool:
    """Trip if `current_time` is somehow called with arguments."""
    return bool(args)


@tool(guardrails=[no_args.input])
def current_time() -> str:
    """Return the current local time as an ISO 8601 string."""
    return datetime.now().isoformat()
```

A tripped guardrail stops the run; `agent.run_sync(...)` comes back with
`status="error"` instead of raising.

## Delegating to Subagents

An agent can hand a conversation off to another agent, or call one as a
tool, via `subagents`:

```python
from runa import Agent


class ResearcherAgent(Agent):
    name = "researcher_agent"
    instructions = "You research topics thoroughly and report back findings."


class GreeterAgent(Agent):
    name = "greeter_agent"
    instructions = "You greet the user, and bring in the researcher for anything factual."
    subagents = [ResearcherAgent.handoff]
```

* `.handoff` transfers the whole conversation to the subagent.
* `.delegate` calls the subagent as a tool and returns its answer to the
  caller, which stays in control.

## Chatting With Your Agent

`runa chat` starts an interactive REPL against any agent's declared
`name`:

```bash
runa chat greeter_agent
```

Every chat persists to `db/runa.db` under a fresh session id. Pick it back
up later:

```bash
runa chat greeter_agent --continue   # most recent session
runa chat greeter_agent --resume     # choose from past sessions
runa chat --list                     # every session in runa.db
runa chat --show SESSION_ID          # replay one session's history
```

## Persisting Conversations in Code

`runa chat` uses `SQLiteSession` under the hood; use it directly to persist
history from your own code:

```python
from runa import SQLiteSession

from app.agents.greeter_agent import GreeterAgent

agent = GreeterAgent()
session = SQLiteSession("user-42")

agent.run_sync("Hi, I'm new here.", session=session)
agent.run_sync("What did I just say?", session=session)
```

With a `session`, prior turns are read from `runa.db` automatically — you
only ever pass the new message.

## Testing Your Agent

`tests/` holds deterministic checks — plain `assert` against a run:

```python
# tests/test_greeter_agent.py
from app.agents.greeter_agent import GreeterAgent


def test_greets_politely():
    run = GreeterAgent().run_sync("Hi")
    assert run.status == "completed"
    assert run.output
```

```bash
runa test
```

`app/evaluations/` holds behavioral evals — grading with a judge model
instead of an assertion:

```bash
runa generate evaluation GreeterAgent
```

```python
# app/evaluations/greeter_agent_eval.py
from runa import Case

from app.agents.greeter_agent import GreeterAgent

agent = GreeterAgent()

dataset = [
    Case(input="Hi there", expected="A warm, one-sentence greeting"),
]
```

```bash
runa eval
```

## Inspecting Traces

Every run is traced to `runa.db`:

```bash
runa traces list
runa traces errors
runa traces show TRACE_ID
```

## What's Next?

* Run `runa generate --help` to see everything scaffolding can create.
* Read the source under `app/agents/`, `app/tools/`, and
  `app/evaluations/` in your generated project — the generated comments
  and docstrings double as reference documentation.
* Keep prompts that grow beyond a line or two in `app/prompts/<name>.md`
  instead of inlining them in Python — omit `instructions` and it's loaded
  from there automatically, creating the file with a `TODO` stub first if
  it doesn't exist yet.
