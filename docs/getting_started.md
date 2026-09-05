# Getting Started with Runa

This guide covers getting up and running with Runa.

After reading it, you will know:

* How to create a new Runa application and configure its model provider.
* How Agent, Tool, and Run fit together, by building one of each.
* How to give an Agent a memory that spans more than one turn.
* How to see exactly what an Agent did, before and after the process exits.
* How to put a human between an Agent's decision and a sensitive action.
* How to run an Agent in the background instead of waiting on it.
* How to tell "it ran" apart from "it did the right thing," with tests and evaluations.

---

## Table of Contents

1. [Guide Assumptions](#1-guide-assumptions)
2. [What is Runa?](#2-what-is-runa)
3. [Creating a New Runa Application](#3-creating-a-new-runa-application)
4. [Configuring the Application](#4-configuring-the-application)
5. [Hello, Runa!](#5-hello-runa)
6. [Agent, Tool, Run: The Trio Behind "Hello"](#6-agent-tool-run-the-trio-behind-hello)
7. [Building the Support Agent](#7-building-the-support-agent)
8. [Giving the Agent a Memory](#8-giving-the-agent-a-memory)
9. [Seeing What Happened](#9-seeing-what-happened)
10. [Requiring Approval for Sensitive Actions](#10-requiring-approval-for-sensitive-actions)
11. [Running in the Background](#11-running-in-the-background)
12. [Testing and Evaluating the Agent](#12-testing-and-evaluating-the-agent)
13. [What's Next?](#13-whats-next)

---

## 1. Guide Assumptions

This guide is written for a developer who is comfortable with Python and
the command line, but has never touched Runa before. It does not assume
any prior experience with agent frameworks, and it does not assume you
know what an "Agent," a "Run," or a "Tool" is yet, those are the first
things this guide builds.

You will need:

* Python 3.14, managed with `uv`.
* An API key for whichever model provider you use (OpenAI or Anthropic,
  in the examples below), set in your environment.

By the end, you will have a small but complete Runa application: a
support Agent with real tools, a memory that spans a conversation, a
sensitive action gated behind human approval, and a test suite.

> **NOTE:** This guide builds one running example from top to bottom. If
> you already know what you're looking for, [docs/guides.md](guides.md)
> is organized as independent recipes instead.

---

## 2. What is Runa?

Runa is an opinionated application framework for agentic AI.

Most agent code today is assembled by hand: a model client, a tool-calling
loop, some ad hoc state, a queue if you're lucky, and no good answer to
"what actually happened during that run?" Runa's position is that this
shouldn't be infrastructure you rebuild per project any more than a web
developer rebuilds routing and persistence per project.

Runa organizes an application around three responsibilities:

```text
Agent
  ↓ declares behavior
Execution
  ↓ progresses it
Run
  ↓ persists it
```

An **Agent** declares what it does and what it can use. **Execution**
is the process of actually calling the model and invoking tools.
A **Run** is the record of one such execution, its input, its state,
everything it did, and what it produced.

You don't need to understand all of that yet. You need one Agent, one
Tool, and one Run, which is exactly what the next few sections build.

---

## 3. Creating a New Runa Application

### 3.1 Installing Runa

Runa is managed with `uv`. Install it as a project dependency:

```bash
uv add runa
```

Confirm the CLI is available:

```bash
$ runa --version
```

### 3.2 Creating the Support Application

Runa applications follow a conventional layout. Scaffold a new one:

```bash
$ runa new support_app
$ cd support_app
```

This creates:

```text
support_app/
├── app/
│   ├── agents/
│   ├── tools/
│   ├── resources/
│   ├── evaluations/
│   └── tests/
├── main.py
├── pyproject.toml
├── .gitignore
└── README.md
```

Nothing here is arbitrary. `app/agents/` is where Agent subclasses live;
`app/tools/` is where Tool subclasses live; `app/evaluations/` and
`app/tests/` separate two things Runa treats as genuinely different
(more on that in [§12](#12-testing-and-evaluating-the-agent)). You will
rarely have to explain this layout to a new contributor, it explains
itself.

`runa generate agent <Name>` and `runa generate tool <Name>` add more
files to this same structure later, so you never have to remember where
a new Agent or Tool is supposed to go.

---

## 4. Configuring the Application

Before an Agent can run, the application needs to know which model
provider to call. This is application-wide configuration, not something
you repeat on every Agent.

Open `main.py`. It already contains:

```python
from runa import configure
from runa.persistence import SQLiteRunStore
from runa.providers import OpenAIProvider

configure(provider=OpenAIProvider(), run_store=SQLiteRunStore("runa.db"))
```

`configure()` sets up the default `Application` (`runa.application`)
that every Agent resolves its provider from. `OpenAIProvider()` reads
`OPENAI_API_KEY` from the environment; swap it for
`AnthropicProvider()` from `runa.providers` if you're using Claude
instead, nothing else in this guide changes.

`SQLiteRunStore("runa.db")` is what lets `runa runs show` find a Run
after this process has exited; you'll use it in
[§9](#9-seeing-what-happened). The library's own default, if you drop
this argument, is in-memory and forgets every Run the moment the process
ends, fine for a quick script, not for an application you intend to
inspect later.

> **NOTE:** `configure(provider="openai")` (a bare string) is shorthand
> for `OpenAIProvider()` when it needs no extra configuration. Pass an
> instance directly, as `main.py` already does, once it needs its own
> `base_url`, client, or other settings.

---

## 5. Hello, Runa!

Before building the real support Agent, prove the machine turns on with
the smallest thing Runa can run. 

```python
# main.py, temporarily
from runa import Agent, configure, tool
from runa.providers import OpenAIProvider

configure(provider=OpenAIProvider())

@tool
def get_weather(city: str) -> str:
    return f"{city}: sunny, 22C"


class WeatherAgent(Agent):
    instructions = "Answer weather questions using the get_weather tool."
    tools = [get_weather]

if __name__ == "__main__":
    run = WeatherAgent.run("What's the weather in Tokyo?")
    print(run.result)
```

Run it:

```bash
$ python main.py
Tokyo is sunny and 22°C.
```

Four lines of application code, an instruction string, a tool, a class,
a call to `.run()`, and you already have a working Agent that decides
when to use a tool and reports back. Nothing about this required a
graph, a orchestration DSL, or a custom execution loop.

Once this works, put `main.py` back to just the `configure(...)` call
from [§4](#4-configuring-the-application), `WeatherAgent` was only here to prove the wiring works. The rest of this guide builds `SupportAgent`
properly, under `app/`, where it belongs.

---

## 6. Agent, Tool, Run: The Trio Behind "Hello"

`WeatherAgent.run(...)` did three distinct things, and it's worth naming
them before building something real:

```text
Agent   → declares behavior:      "answer weather questions, using this tool"
Tool    → provides a capability:  get_weather(city) -> str
Run     → records the execution:  what was asked, what happened, what came back
```

**The Agent** is a plain Python class. `instructions` and `tools` are
class attributes, you can see everything an Agent is capable of by
reading its class body, without running anything.

**The Tool** is how an Agent reaches outside itself. `@tool` turns an
ordinary function into one: its name, description, and input schema are
inferred from the function's name, docstring, and type annotations. When
a tool needs more than a function body, approval, idempotency, other
class-level configuration, subclass `Tool` instead:

```python
from runa import Tool


class WebSearch(Tool):
    def call(self, query: str) -> str:
        return search_web(query)
```

Both forms are interchangeable in `tools = [...]`.

**The Run** is what `.run(...)` returns. It's not just the model's final
answer, it's the full record of that invocation: input, state, every
event that happened along the way, and the result. You already used one
field of it, `run.result`; [§9](#9-seeing-what-happened) uses the rest.

One Agent produces many Runs. Changing `WeatherAgent`'s instructions
tomorrow does not retroactively change the Run you just printed, each
Run is a snapshot of one execution against the Agent as it was defined
at that moment.

---

## 7. Building the Support Agent

With the vocabulary in place, build something closer to a real
application: an Agent that answers customer questions and, when it
can't resolve one, opens a ticket.

### 7.1 Generating the Agent

```bash
$ runa generate agent Support
```

This writes `app/agents/support_agent.py`:

```python
from runa import Agent


class SupportAgent(Agent):
    instructions = """
    TODO: describe what SupportAgent does.
    """
    tools = []
```

### 7.2 Generating a Tool

A support Agent needs something to search with. Generate a tool:

```bash
$ runa generate tool KnowledgeBase
```

This writes `app/tools/knowledge_base_tool.py` with a stub `call()`.
Fill it in:

```python
from runa import Tool


class KnowledgeBaseTool(Tool):
    """Search the knowledge base for an answer."""

    def call(self, query: str) -> str:
        # Replace with a real lookup against your knowledge base.
        return search_knowledge_base(query)
```

And a second one for opening a ticket:

```bash
$ runa generate tool CreateTicket
```

```python
from runa import Tool


class CreateTicketTool(Tool):
    """Open a support ticket for an issue that couldn't be resolved."""

    def call(self, summary: str) -> str:
        ticket = tickets.create(summary=summary)
        return f"Created ticket {ticket.id}"
```

### 7.3 Wiring Them to the Agent

```python
# app/agents/support_agent.py
from runa import Agent

from app.tools.knowledge_base_tool import KnowledgeBaseTool
from app.tools.create_ticket_tool import CreateTicketTool


class SupportAgent(Agent):
    instructions = """
    Help customers resolve support issues.
    Search the knowledge base first.
    Create a ticket only when the issue cannot be resolved from it.
    """

    tools = [KnowledgeBaseTool, CreateTicketTool]
```

Notice what's absent: no graph connecting "search" to "create ticket," no
state machine describing the decision. The instructions say what to do;
the model decides, at each step, which tool (if any) to call. This is
what manifesto §8 means by "standardize execution, not intelligence",
Runa gives you one execution lifecycle, not a required theory of how the
Agent should think.

### 7.4 Running It

From the command line:

```bash
$ runa run Support "My invoice looks wrong, the total is off by $12."
Run 8f3a... (completed)
I found a known billing rounding issue in the knowledge base and opened
ticket #4471 so billing can correct the $12 difference on your account.
```

`runa run <Agent> <input>` matches `Support` against `SupportAgent`
(the `Agent` suffix is optional, following the same convention
`runa generate agent` uses) and is equivalent to importing it into
`main.py` and calling `SupportAgent.run(...)` directly, the CLI's
version additionally saves the Run to the store configured in
[§4](#4-configuring-the-application), which is what makes
[§9](#9-seeing-what-happened) work without any extra code.

---

## 8. Giving the Agent a Memory

Right now, every call to `SupportAgent.run(...)` starts from nothing. A
real support interaction is rarely one message, the customer follows up,
and the Agent needs to remember what was already said.

A `Conversation` is state that spans multiple Runs:

```python
from runa import Conversation

conversation = Conversation()

run1 = SupportAgent.run(
    "My invoice is wrong.",
    conversation=conversation,
)

run2 = SupportAgent.run(
    "What should I do next?",
    conversation=conversation,
)
```

`run2` sees the history from `run1` through `conversation`. The Run
remains the execution boundary, each call still produces its own Run,
with its own events and result, but the Conversation carries context
between them.

Two things worth knowing before you rely on this:

* **Sequence, don't race.** Only run Agents against the same
  Conversation one after another. Two Runs launched concurrently against
  one Conversation (say, both via `run_later()`) aren't merged, each
  seeds its history from the Conversation as it stood when it started,
  and whichever finishes last silently overwrites the other's turn.
* **A Conversation doesn't survive a restart on its own.** It lives in
  memory, same as a Run, until you save it:

  ```python
  from runa.persistence import SQLiteConversationStore

  conversation_store = SQLiteConversationStore("conversations.db")
  conversation_store.save(conversation)

  # later, in a new process:
  conversation = conversation_store.get(conversation_id)
  ```

  Unlike a Run saved via `run_later()`, nothing does this for you
  automatically, save it yourself after each turn you want to survive
  a restart.

---

## 9. Seeing What Happened

A Run is more than its `.result`. It recorded every meaningful thing
that happened while it executed, which means you can answer "what did
the Agent actually do?" without adding any tracing code to
`SupportAgent` itself.

In-process, this is always available, with no setup:

```python
from runa.observability import timeline

run = SupportAgent.run("My invoice is wrong.")
for entry in timeline(run):
    print(entry.timestamp, entry.summary)
```

```text
2026-09-05T10:02:11  Run started
2026-09-05T10:02:11  Model called
2026-09-05T10:02:12  Tool called: KnowledgeBaseTool
2026-09-05T10:02:12  Tool completed
2026-09-05T10:02:13  Model called
2026-09-05T10:02:13  Run completed
```

Because `main.py` configured a `SQLiteRunStore` in
[§4](#4-configuring-the-application), and `runa run` saves every Run to
it, the same information is available from the command line after the
process has exited, for a Run you ran minutes or days ago:

```bash
$ runa runs show 8f3a...
Run 8f3a... (completed): SupportAgent
2026-09-05T10:02:11  Run started
2026-09-05T10:02:11  Model called
2026-09-05T10:02:12  Tool called: KnowledgeBaseTool
2026-09-05T10:02:12  Tool completed
2026-09-05T10:02:13  Model called
2026-09-05T10:02:13  Run completed

$ runa runs list --status failed --agent-name SupportAgent
no runs found
```

If you call `SupportAgent.run(...)` directly instead of going through
`runa run` (as in a script, or a web handler), save it yourself when you
want this available later:

```python
from runa import application

run = SupportAgent.run("My invoice is wrong.")
application.run_store.save(run)
```

The event history is meant to be useful during development, not only
after something goes wrong in production, reach for `timeline(run)` the
same way you'd reach for a debugger, before reaching for print
statements scattered through your tool code.

---

## 10. Requiring Approval for Sensitive Actions

`CreateTicketTool` is harmless to let the model call freely. Not every
tool is. Suppose the support Agent grows a `RefundCustomer` tool,
something you want a human to sign off on before it actually happens.

Declare that at the Agent boundary:

```python
from app.tools.refund_customer_tool import RefundCustomerTool


class SupportAgent(Agent):
    tools = [KnowledgeBaseTool, CreateTicketTool, RefundCustomerTool]

    requires_approval = [RefundCustomerTool]
```

When execution reaches that tool call, the Run pauses instead of
executing it:

```text
Running → AwaitingApproval → Approved → Running
                            → Denied   → Failed / Cancelled
```

A human resolves it from the CLI:

```bash
$ runa runs pending
a91c...  awaiting_approval  SupportAgent  2026-09-05T10:05:02

$ runa runs approve a91c... <tool_call_id>
```

or denies it, with a reason, which fails the Run instead:

```bash
$ runa runs deny a91c... <tool_call_id> --reason "amount exceeds policy"
```

This is a lifecycle transition on the same Run, not a separate workflow
system bolted on beside it, the Run you'd inspect with
`runa runs show` is the same one whether or not it ever paused for
approval.

For rules the application can decide on its own, without a human,
`policies` sits earlier in the same chain and can veto a call outright:

```python
def block_large_refunds(run, tool_call) -> bool:
    return tool_call.arguments.get("amount", 0) <= 500


class SupportAgent(Agent):
    tools = [KnowledgeBaseTool, CreateTicketTool, RefundCustomerTool]
    policies = [block_large_refunds]
    requires_approval = [RefundCustomerTool]
```

Use `policies` for what's always true regardless of who's watching; use
`requires_approval` for the decisions that should always go to a person.
The underlying principle, stated once in
[RUNA.md](../RUNA.md#7-capabilities-do-not-imply-authority): **intelligence
does not imply authority.**

---

## 11. Running in the Background

Everything so far has run synchronously, `.run(...)` blocks until the
Agent finishes. Some work (a long research task, a report) shouldn't
hold up the caller. Runa doesn't introduce a separate job system for
this; it's the same Run, advanced differently:

```python
run = SupportAgent.run_later("Draft a detailed billing summary for the last quarter.")
```

The caller gets the Run back immediately; a Queue advances it. With the
`SQLiteRunStore` already configured, `run_later()` saves the Run to it
automatically once before dispatch and again at its next pause point
(completion, failure, or an approval gate), so `runa runs show <id>`
reflects what actually happened, no extra wiring required.

Three ways to advance the same kind of Run:

```text
agent.run(...)         caller blocks until the Run finishes
agent.run_async(...)   caller awaits the Run; I/O runs concurrently
agent.run_later(...)   caller gets the Run immediately; a Queue advances it
```

If the process can crash mid-Run and losing that progress is
unacceptable, use a `DurableQueue` (`SQLiteQueue`) instead of the
default `InlineQueue`, and recover orphaned Runs once at startup:

```python
from runa import recover_pending

recover_pending(queue, application.run_store, executor, agents=[SupportAgent])
```

Recovery restarts a recovered Run from the beginning, not from wherever
it crashed, so only pass Agents whose tools are all
`idempotent = True`, or a real side effect (a refund, an email) can
happen twice. See
[Running in the Background](guides.md#running-in-the-background) for the
full treatment, including shutting a queue down cleanly.

---

## 12. Testing and Evaluating the Agent

`SupportAgent` calls a real model, which means the same input can
produce a differently worded, but equally correct, answer each time.
That's exactly why Runa keeps two separate questions apart:

```text
Tests         verify deterministic invariants about your application
Evaluations   measure probabilistic behavior of the Agent
```

A test asserts a fact that must always hold:

```python
# app/tests/test_support_agent.py
from app.agents.support_agent import SupportAgent


def test_support_agent_completes():
    run = SupportAgent.run("My invoice is wrong.")
    assert run.completed
```

An evaluation grades something a plain assertion can't, whether the
answer was actually good:

```bash
$ runa generate evaluation Support
```

```python
# app/evaluations/support_eval.py
from runa import EvalCase, expect

from app.agents.support_agent import SupportAgent

agent = SupportAgent()

cases: list[EvalCase] = [
    EvalCase(
        name="resolves a billing question",
        input="My invoice is wrong, the total is off by $12.",
        check=lambda run: expect(run).to_be_completed().to_meet_the_goal(),
    ),
]
```

Both run against the exact same `Agent`/`Run` path production uses —
there's no separate mock architecture to keep in sync:

```bash
$ runa test    # app/tests/, deterministic invariants
$ runa eval    # app/evaluations/, probabilistic behavior
```

If `runa test` is red, something in your application broke. If
`runa eval` is red, the Agent's behavior needs attention, a different
kind of failure, and now you have a way to see both.

---

## 13. What's Next?

You now have a small, complete Runa application: an Agent with two tools,
a conversation that remembers earlier turns, a sensitive action gated
behind approval, background execution, and a test suite that tells tests
and evaluations apart.

From here:

* [docs/concepts.md](concepts.md), the full vocabulary (Context, State,
  Capability, Event, Artifact) this guide only used pieces of.
* [docs/guides.md](guides.md), independent recipes for the same
  patterns above, plus a few this guide didn't cover: delegating to
  another Agent, retrying transient model errors, bounding a Run's
  wall-clock time.
* [docs/cli.md](cli.md), the full `runa` command reference.
* [RUNA.md](../RUNA.md), the design principles behind all of the above,
  if you want to know *why* Runa is shaped this way before you extend it.

> **TIP:** When you're unsure whether something needs a new abstraction,
> RUNA.md's own checklist is the fastest way to decide: does it simplify
> the common case, does it belong to an existing Agent/Execution/Run/
> Context/State/Capability, and does it preserve an escape hatch? If not,
> it probably doesn't belong in the core.
