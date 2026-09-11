# Getting Started with Runa

This guide covers everything you need to build your first Runa agent application. 

After reading this guide, you will know how to:

* How to install Runa, create a new Runa application, and chatting with an Agent.
* The general layout of a Runa application.
* The basic principles of Agentics.
* How to quickly generate the starting pieces of a Runa application.
* Test and evaluate your agent
* How to deploy your app to production.

## 1. Introduction

Welcome to Runa! In this guide, we'll walk through the core concepts of building agent 
applications with Runa. You don't need any experience with Runa to follow along with this guide.

Runa is an agentic framework built with Python programming language. 
Runa takes advantage of many features of Python so we strongly recommend learning 
the basics of Python so that you understand some of the basic terms and vocabulary you will see in tutorial.

- [Official Python Programming Language website](https://www.python.org)
- [List of Free Programming Books](https://github.com/EbookFoundation/free-programming-books/blob/main/books/free-programming-books-langs.md#python)

## 2. Runa Philosophy

Runa is an agentic application development framework written in the Python programming language. 
It is designed to make programming agentic applications easier by making assumptions about what 
every developer needs to get started. It allows you to write less code while accomplishing 
more than many other SDKs and frameworks.

Runa is opinionated software. It makes the assumption that there is a "best" way to do things, 
and it's designed to encourage that way - and in some cases to discourage alternatives. 
If you learn "The Runa Way" you'll probably discover a tremendous increase in productivity. 
If you persist in bringing old habits from other frameworks to your Runa development, 
and trying to use patterns you learned elsewhere, you may have a less happy experience.

The Runa philosophy includes two major guiding principles:

- Convention Over Configuration: Runa has opinions about the best way to do many things in an agentic application, 
  and defaults to this set of conventions, rather than require that you define them yourself through endless 
  configuration files.
- Don't Repeat Yourself: DRY is a principle of software development which states that 
  "Every piece of knowledge must have a single, unambiguous, authoritative representation within a system". 
  By not writing the same information over and over again, our code is more maintainable, more extensible, and less buggy.

## 3. Creating a New Runa Application

We're going to build a project called `code-editor` - a simple agent app that demonstrate several of Runa's
built-in features.

### Installing Runa

Runa needs Python 3.14. Install it with [uv](https://docs.astral.sh/uv/):

### 3.1. Prerequisites

1. Install [uv](https://docs.astral.sh/uv/getting-started/installation/)
2. Install [Python 3.14](https://www.python.org/downloads/):
3. Install Runa

    ```bash
    uv init
    uv venv
    source .venv/bin/activate
    uv add git+https://github.com/benybrahim/runa.git
    ```

### Creating the Application

`runa new` scaffolds a new application with everything you need:

```bash
runa new code-editor
cd code-editor
```

Take a look at what was generated:

```
code-editor/
├── app/
│   ├── agents/          # Agent subclasses
│   ├── guardrails/      # input and output guardrails
│   ├── prompts/         # prompt text
│   └── tools/           # @tool-decorated functions
├── config/              # shared config (clients, settings)
├── db/                  # runa.db: sessions/memory/knowledge/traces ...
├── docs/                # application docs
├── evals/               # eval cases, run with `runa eval`
├── tests/               # deterministic tests, run with `runa test`
├── main.py              # application entry point, loads .env
├── Dockerfile            
├── .env                  # your model's API key — fill this in, never commit it
└── pyproject.toml
```

Open `.env` and set the API key for whichever model your agents will use, for example:

```
OPENAPI_API_KEY=sk-...
```

That's the only configuration step. Nothing else needs to be wired up
globally, a model is a per-`Agent` attribute, and Runa resolves it to the
right provider by name.

## Hello, Runa!

Let's generate an agent:

```bash
runa generate agent GreeterAgent --model gpt-5.4-nano --instruction "Say Hello!"
```

This creates `app/agents/greeter_agent.py`:

```python
from runa import Agent


class GretterAgent(Agent):
    name = "code_agent"
    model = "gpt-5.4-nano"
```

It will also automatically create `app/prompts/greeter_agents.md`, 
and `CodeAgent` will load his instructions by default automatically from there.

```markdown
You write and edit code for the user, one file at a time.
```

Run it from `main.py`, or straight from a Python shell:

```python
from runa import Agent


class GreeterAgent(Agent):
    name = "greeter_agent"
    model = "gpt-5.4-nano"


run = GreeterAgent.run_sync("Say Hello!")
```

`run_sync/run` returns a `Run` with: 
- **output**: the agent final output; `None` when `status == "error"`
- **trace**: The hierarchical trace (agent/LLM/tool/guardrail spans) for that call
- **usage**: token usage for this call (same value as agent.last_usage afterward) 
- **status**: "completed" | "error" - default to `"completed"`
- **error**: the exception message when `status == "error"`
- **metdata**: reserved for future per-run detail, empty by default

You can also chat with your agent using:

```bash
runa chat code_agent
```


## Giving Your Agent Tools

A tool is a plain Python function. Its signature *is* its schema, Runa
reads the type hints and the docstring, so there's nothing else to declare.

```bash
runa generate tool --name current_time
```

```python
# app/tools/core.py
from datetime import datetime

from runa import tool


@tool
def current_time() -> str:
    """Return the current local time as an ISO 8601 string."""
    return datetime.now().isoformat()
```

Every tool you generate without a module prefix lands in this same
catch-all `app/tools/core.py` file. Once it grows crowded, group related
tools into their own file with `module:function`, e.g. `runa generate tool
--name weather:forecast` writes `app/tools/weather.py`.

Attach it to an agent with `tools`:

```python
from runa import Agent

from app.tools.core import current_time


class GreeterAgent(Agent):
    name = "greeter_agent"
    instructions = "You greet the user warmly, and tell them the time if asked."
    tools = [current_time]
```

The model decides on its own when to call `current_time`, by checking your request and tool description match.

## Adding Guardrails

A guardrail is a function tha return a boolean. It basically check conditons on agent and tools 
inputs, outputs. Bind it to `.input` or `.output` to say which side it checks.

```python
from runa import Agent, guardrail

from app.tools.core import current_time


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

`runa chat` uses `SQLiteSession` under the hood by default; use it directly to persist
history from your own code:

```python
from runa import SQLiteSession

from app.agents import GreeterAgent

agent = GreeterAgent()
session = SQLiteSession("user-42")

agent.run_sync("Hi, I'm new here.", session=session)
agent.run_sync("What did I just say?", session=session)
```

With a `session`, prior turns are read from `runa.db` automatically, you
only ever pass the new message.



`evals/` holds behavioral evals, grading with a judge model instead of an
assertion:

```bash
runa generate evaluation greeter_agent
```

```python
# evals/greeter_agent_eval.py
from runa import Case

from app.agents import GreeterAgent

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