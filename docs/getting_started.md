# Getting Started with Runa

This guide builds one small Runa application, start to finish: an Agent,
a Tool, and a Run.

---

## Contents

1. [What is Runa?](#1-what-is-runa)
2. [Setup](#2-setup)
3. [Hello, Runa](#3-hello-runa)
4. [Agent, Tool, Run](#4-agent-tool-run)
5. [A Real Agent](#5-a-real-agent)
6. [Memory](#6-memory)
7. [What Happened](#7-what-happened)
8. [Approval](#8-approval)
9. [Background](#9-background)
10. [Tests and Evaluations](#10-tests-and-evaluations)
11. [Next](#11-next)

---

## 1. What is Runa?

Three responsibilities, three concepts:

```text
Agent      declares behavior
Execution  progresses it
Run        persists it
```

An Agent says what it does and what it can use. Execution calls the
model and invokes tools. A Run is the record: input, state, everything
that happened, the result.

That's the whole model. Everything below is one of these three things.

---

## 2. Setup

Needs Python 3.14 (via `uv`) and an API key for your model provider.

```bash
uv add git+https://github.com/Benybrahim/runa
runa new support_app
cd support_app
```

This scaffolds:

```text
support_app/
├── app/
│   ├── agents/
│   ├── tools/
│   ├── evaluations/
│   └── tests/
├── main.py
└── pyproject.toml
```

`main.py` already configures the application:

```python
from runa import configure
from runa.persistence import SQLiteRunStore
from runa.providers import OpenAIProvider

configure(
    run_store=SQLiteRunStore("runa.db"),
)
```

Swap in `AnthropicProvider()` for Claude, nothing else changes.
`run_store` is what lets `runa runs show` find a Run after this process
has exited ([§7](#7-what-happened)).

---

## 3. Hello, Runa

```python
from runa import Agent, configure, tool

@tool
def get_weather(city: str) -> str:
    return f"{city}: sunny, 22C"


class WeatherAgent(Agent):
    instructions = "Answer weather questions using the get_weather tool."
    tools = [get_weather]


run = WeatherAgent.run_sync("What's the weather in Tokyo?")
print(run.result)
```

```bash
$ python main.py
Tokyo is sunny and 22°C.
```

No graph. No orchestration. An instruction, a tool, a call.

---

## 4. Agent, Tool, Run

```text
Agent   answer weather questions, using this tool
Tool    get_weather(city) -> str
Run     what was asked, what happened, what came back
```

An Agent is a plain class. `instructions` and `tools` are class
attributes, readable without running anything.

A Tool is how an Agent reaches outside itself. `@tool` turns a function
into one. Subclass `Tool` directly when it needs more, approval,
idempotency, other configuration:

```python
from runa import Tool


class WebSearch(Tool):
    def call(self, query: str) -> str:
        return search_web(query)
```

A Run is what `run_sync()` returns: not just the answer, the full
record of the execution.

---

## 5. A Real Agent

```bash
runa generate agent Support
runa generate tool KnowledgeBase
runa generate tool CreateTicket
```

Fill in the tools:

```python
from runa import Tool


class KnowledgeBaseTool(Tool):
    """Search the knowledge base for an answer."""

    def call(self, query: str) -> str:
        return search_knowledge_base(query)


class CreateTicketTool(Tool):
    """Open a support ticket for an issue that couldn't be resolved."""

    def call(self, summary: str) -> str:
        ticket = tickets.create(summary=summary)
        return f"Created ticket {ticket.id}"
```

Wire them to the Agent:

```python
from runa import Agent


class SupportAgent(Agent):
    instructions = """
    Help customers resolve support issues.
    Search the knowledge base first.
    Create a ticket only when the issue cannot be resolved from it.
    """
    delegations = [KnowledgeBaseTool, CreateTicketTool]
```

No graph connects search to ticket-creation. The instructions say what
to do; the model decides what to call.

```bash
$ runa run Support "My invoice looks wrong, the total is off by $12."
I found a known billing rounding issue and opened ticket #4471.
```

---

## 6. Memory

A `Conversation` carries state across Runs:

```python
from runa import Conversation

conversation = Conversation()

SupportAgent.run_sync("My invoice is wrong.", conversation=conversation)
SupportAgent.run_sync("What should I do next?", conversation=conversation)
```

The second call sees the first. Each call still produces its own Run.

Run Agents against one Conversation one at a time, not concurrently.

A Conversation lives in memory until saved:

```python
from runa.persistence import SQLiteConversationStore

store = SQLiteConversationStore("conversations.db")
store.save(conversation)

# later, in a new process
conversation = store.get(conversation_id)
```

---

## 7. What Happened

```python
from runa.observability import timeline

run = SupportAgent.run_sync("My invoice is wrong.")
for entry in timeline(run):
    print(entry.timestamp, entry.summary)
```

```text
Run started
Model called
Tool called: KnowledgeBaseTool
Tool completed
Model called
Run completed
```

`runa run` saves every Run to the configured store, so the same
history is available from the CLI after the process exits:

```bash
$ runa runs show <id>
```

Calling `run_sync()` directly instead of `runa run`? Save it yourself:

```python
from runa import application

run = SupportAgent.run_sync("My invoice is wrong.")
application.run_store.save(run)
```

---

## 8. Approval

Some actions need a human. Declare that on the tool:

```python
from runa import Tool


class RefundCustomerTool(Tool):
    requires_approval = True

    def call(self, order_id: str, amount: float) -> str: ...
```

```text
Running → AwaitingApproval → Approved → Running
                            → Denied   → Failed
```

```bash
$ runa runs pending
$ runa runs approve <run_id> <tool_call_id>
$ runa runs deny <run_id> <tool_call_id> --reason "amount exceeds policy"
```

For rules the application can decide on its own, use `policies`
instead:

```python
def block_large_refunds(run, tool_call) -> bool:
    return tool_call.arguments.get("amount", 0) <= 500


class SupportAgent(Agent):
    tools = [KnowledgeBaseTool, CreateTicketTool, RefundCustomerTool]
    policies = [block_large_refunds]
```

Intelligence does not imply authority.

---

## 9. Background

```python
run = SupportAgent.run_later(
    "Draft a detailed billing summary for the last quarter."
)
```

Same Run, advanced differently:

```text
run()         await it
run_sync()    block on it
run_stream()  stream it
run_later()   queue it
```

If a crash mid-Run can't be allowed to lose progress, use a
`DurableQueue` and recover at startup:

```python
from runa import recover_pending

recover_pending(queue, application.run_store, executor, agents=[SupportAgent])
```

Recovery restarts from the beginning, not from where it crashed. Only
recover Agents whose tools are all `idempotent = True`.

---

## 10. Tests and Evaluations

```text
Tests         deterministic invariants
Evaluations   probabilistic behavior
```

```python
def test_support_agent_completes():
    run = SupportAgent.run_sync("My invoice is wrong.")
    assert run.completed
```

```python
from runa import EvalCase, expect

cases = [
    EvalCase(
        name="resolves a billing question",
        input="My invoice is wrong, the total is off by $12.",
        check=lambda run: expect(run).to_be_completed().to_meet_the_goal(),
    ),
]
```

```bash
runa test
runa eval
```

Both run the same Agent, the same Run. No mock architecture to keep in
sync.

---

## 11. Next

* [concepts.md](concepts.md) — the full vocabulary
* [cli.md](cli.md) — the `runa` command reference
* [RUNA.md](../RUNA.md) — why Runa is shaped this way
