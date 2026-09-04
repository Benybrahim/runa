# Getting Started

Runa is designed so that an agent application can start with ordinary application code.

The basic model is small:

```text
Agent
  ↓
Run
  ↓
Result
```

Runa supplies the machinery around the Run.

---

## 1. Create a Project

Create a new Runa application:

```bash
runa new research_app
cd research_app
```

A conventional project looks like:

```text
research_app/
├── app/
│   ├── agents/
│   ├── tools/
│   ├── resources/
│   ├── evaluations/
│   └── tests/
├── main.py
└── ...
```

The project structure is conventional on purpose.

Structure carries meaning.

`runa generate agent <Name>` scaffolds a new agent module under `app/agents/`
following that same convention. `runa generate tool <Name>` and `runa generate
evaluation <Name>` do the same for `app/tools/` and `app/evaluations/`.

---

## 2. Configure the Application

Runa keeps application-wide infrastructure in one place: an `Application`.
It owns the shared runtime an Agent needs but shouldn't have to repeat —
today that's the model provider and the Run store; persistence, execution,
telemetry, and other infrastructure grow the same `Application` rather than
becoming their own configuration path.

A minimal `main.py` configures the model provider:

```python
from runa import configure
from runa.providers.openai import OpenAIProvider

configure(provider=OpenAIProvider())
```

The exact provider depends on the model service your application uses.

Configuration should be application-level rather than repeated across every Agent.

`configure(...)` is sugar for configuring the default `Application` —
`runa.application` — that every Agent resolves its provider from:

```python
import runa

runa.configure(provider=OpenAIProvider())
assert runa.application.provider is not None
```

Construct an explicit `Application()` instead when you need isolated
infrastructure — most commonly in tests, where a `FakeProvider` on one
`Application` should never leak into another test's:

```python
app = runa.Application()
app.configure(provider=OpenAIProvider())
```

An explicit `Application` doesn't change how Agents run: pass its provider
into an `Executor` yourself (`Executor(provider=app.provider)`) and hand it
to `Agent.run(executor=...)`, the same escape hatch every Agent already
supports.

---

## 3. Create an Agent

Create an Agent:

```python
from runa import Agent


class ResearchAgent(Agent):
    instructions = """
    Research questions carefully.
    Prefer reliable sources.
    Cite important claims.
    """

    tools = [WebSearch]
```

The Agent definition should make its responsibility and capabilities visible.

A simple Agent does not require a graph, workflow, memory system, or custom execution engine.

---

## 4. Run the Agent

Execute the Agent:

```python
run = ResearchAgent.run("What are the most promising approaches to fusion energy?")
```

The return value is a `Run`.

The Run represents this execution from beginning to end.

You can inspect its result:

```python
print(run.result)
```

And, when supported by the application:

```python
print(run.status)
print(run.events)
print(run.artifacts)
```

---

## 5. Understand the Run

A Run is more than a model response.

Conceptually:

```text
Run
├── Input
├── Goal / intent
├── Context
├── State
├── Events
├── Actions
├── Artifacts
├── Result
└── Status
```

This means the same execution can later be observed, persisted, evaluated, or resumed without changing the programming model.

---

## 6. Add a Tool

An Agent becomes useful when it can interact with the application or the outside world.

A simple function can become a Tool with `@tool`. Its name, description, and
input schema are inferred from the function's name, docstring, and type
annotations:

```python
from runa import tool


@tool
def web_search(query: str) -> str:
    """Search the web for information."""
    return search_web(query)
```

Then declare it on the Agent:

```python
class ResearchAgent(Agent):
    instructions = """
    Research questions carefully.
    Prefer reliable sources.
    """

    tools = [web_search]
```

For a tool that needs more than a function body — approval, idempotency, or
other class-level configuration — subclass `Tool` instead:

```python
from runa import Tool


class WebSearch(Tool):
    def call(self, query: str):
        return search_web(query)
```

Tools should expose clear structured inputs and explicit outputs.

---

## 7. Use Application Objects

Agents belong inside applications.

Your application can contain ordinary domain objects:

```python
class Customer: ...


class ResearchProject: ...
```

An Agent can operate on those objects without turning them into Agent-specific abstractions.

This keeps the application domain separate from agent execution.

---

## 8. Use Conversation State

A Conversation spans multiple Runs.

Conceptually:

```python
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

The Conversation survives across Runs.

The Run remains the execution boundary.

---

## 9. Run in the Background

The same Agent can execute later:

```python
run = ResearchAgent.run_later("Produce a detailed report on fusion energy.")
```

This is still a Run.

The difference is when and where it advances.

You do not need a separate job programming model for agent work.

---

## 10. Observe a Run

Because execution produces Events, a Run can be inspected after execution.

A typical timeline may contain:

```text
Run Started
Model Called
Tool Called: WebSearch
Tool Completed
Artifact Created: Report
Run Completed
```

The goal is simple:

> Understand what happened without adding tracing code to every Agent.

`timeline(run)` reads this straight off the `Run` object, so it works
in-process with no setup. The `runa runs show <id>` CLI form below reads it
back from a `RunStore` instead, so it only sees Runs that were actually
saved there.

---

## 11. Evaluate an Agent

Tests can verify application invariants:

```python
assert run.completed
assert report_created
```

Evaluations measure probabilistic behavior:

```python
expect(run).to_be_factual()
expect(run).to_meet_the_goal()
```

Evaluation should exercise the same Agent and Run semantics used by the application.

The generated project wires both into the CLI:

```bash
runa test    # app/tests/ — deterministic invariants
runa eval    # app/evaluations/ — probabilistic behavior
```

You can also inspect a Run's execution directly from the CLI, once it's
been saved to a `RunStore` — automatic for `run_later()` given a
`DurableQueue`, or call `runa.application.run_store.save(run)` yourself after a
synchronous `run` (or a backgrounded one on the default `InlineQueue`):

```bash
runa runs show <id>
runa runs list --status failed
```

---

## 12. Customize Only When Needed

The normal path should remain simple.

Reach for custom runtime strategies, infrastructure adapters, or lower-level APIs only when the application actually needs them.

Runa's defaults are the starting point, not the boundary of what the framework can do.

# The Mental Model

When building a Runa application, start with three questions:

```text
What should this Agent do?

What should a Run accomplish?

What capabilities does the Agent need?
```

Then let Runa handle the machinery around execution.

> **Start with the application. Add infrastructure only when the application needs it.**
