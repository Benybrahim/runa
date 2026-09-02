# The RUNA Doctrine

RUNA is an opinionated framework for building agent applications.

It is built around one central idea:

> **The primary unit of computation in an agent application is the Run.**

For the broader philosophy and reasoning behind these principles, see [the RUNA Manifesto](./docs/manifesto.md).

---

## 1. Optimize for Developer Happiness

Developer happiness is a serious technical concern.

Building a useful agent should begin with intent, not infrastructure.

A developer should be able to write:

```python
class ResearchAgent(Agent):
    instructions = """
    Research questions carefully.
    Prefer reliable sources.
    Cite important claims.
    """

    tools = [WebSearch]
```

without first configuring an execution graph, model client, message manager, tracing provider, memory backend, and evaluation system.

These concerns exist.

They should not be the cost of getting started.

Complexity should be available when needed.

It should not be mandatory.

---

## 2. Convention Over Configuration

Agent applications contain recurring patterns.

Agents use tools.

Runs have state.

Executions produce events.

Agents create artifacts.

Runs can be observed, persisted, retried, and evaluated.

Developers should not repeatedly configure these relationships.

RUNA should infer common behavior from clear conventions.

Structure is configuration.

Names are configuration.

Types are configuration.

Explicit configuration should be reserved for decisions that are genuinely application-specific.

When developers follow RUNA's conventions, the application should work.

---

## 3. Omakase Agent Infrastructure

Agent development should not require assembling an infrastructure stack before building an application.

RUNA provides an integrated default environment for:

* agent execution
* model integration
* tools
* run state
* persistence
* background execution
* observability
* evaluation
* human approval

Individual components may be replaced when necessary.

But developers should not need to become system integrators before they can become application developers.

RUNA makes decisions so developers can focus on theirs.

---

## 4. Agents Are Objects, Not Graphs

An agent should first be understandable as an object with behavior and capabilities.

```python
class SupportAgent(Agent):
    tools = [KnowledgeBase, CreateTicket]

    instructions = """
    Help customers resolve support issues.
    Create a ticket when the issue cannot be resolved.
    """
```

Graphs, workflows, and state machines can be useful.

They are not the fundamental programming model.

Most agent applications should be expressed as ordinary application code.

Graphs are tools for modeling relationships.

They should not be required to express behavior.

---

## 5. The Run Is the Primary Unit of Computation

Every execution of an agent creates a Run.

```python
run = ResearchAgent.run("What are the most promising approaches to fusion energy?")
```

A Run represents the complete execution of an agent.

It contains:

```text
Run
├── Input
├── Context
├── State
├── Messages
├── Events
├── Actions
├── Artifacts
├── Result
└── Status
```

A Run may execute synchronously or in the background.

It may complete, fail, pause, await approval, or resume.

These are all properties of the same fundamental abstraction.

The Run provides a common model for execution, persistence, observability, retries, and evaluation.

---

## 6. One Lifecycle, Many Strategies

RUNA provides a consistent execution lifecycle.

It does not prescribe a theory of intelligence.

Some agents simply answer.

Some use tools.

Some plan.

Some delegate.

Some reflect.

Some are deterministic.

Some are probabilistic.

Planning is not mandatory.

Reflection is not mandatory.

Multi-agent systems are not mandatory.

The simplest agent should remain simple.

```python
class Translator(Agent):
    instructions = """
    Translate English into Japanese.
    """
```

Advanced behavior should be opt-in.

RUNA standardizes execution without standardizing thought.

---

## 7. State Is Explicit

"Memory" is too vague.

RUNA distinguishes different forms of state.

### Run State

State that exists for a single execution.

### Conversation State

State that persists across interactions.

### Application State

Durable state belonging to the application domain.

These states have different lifetimes and responsibilities.

They should not be hidden behind one universal memory abstraction.

Developers should know what exists temporarily, what persists between interactions, and what belongs to the application itself.

---

## 8. Observability and Evaluation Are Defaults

Agent execution is probabilistic.

A successful run may take an unexpected path.

A failed run may not have a traditional stack trace explaining what happened.

Observability is therefore part of development.

Every Run should be inspectable.

Developers should be able to understand:

* what input the agent received
* what actions it took
* which tools it used
* how state changed
* what artifacts it created
* why execution failed

without manually adding tracing infrastructure to every agent.

Evaluation is equally fundamental.

An agent that executes successfully is not necessarily correct.

Tests verify application invariants.

Evaluations measure agent behavior.

Both should be natural parts of development.

---

## 9. Provide Sharp Knives

RUNA provides strong defaults.

It does not trap developers inside abstractions.

Developers should be able to inspect runs, access state, invoke models directly, execute tools directly, override runtime behavior, and integrate external systems.

Abstractions should make common behavior easy.

They should not become prisons.

RUNA provides conventions and escape hatches.

---

# The RUNA Standard

Before adding a feature or abstraction to RUNA, ask:

* Does it make the common case simpler?
* Does it follow an existing convention?
* Does it make agent behavior easier to understand?
* Does it belong naturally to a Run?
* Does it make capabilities more explicit?
* Does it improve observability?
* Can RUNA provide a good default?
* Does it make evaluation easier?
* Does it preserve an escape hatch?

If the answer is no, the feature may not belong in the core framework.

---

# The Goal

RUNA is not trying to be the most configurable agent framework.

It is not trying to be the most abstract.

It is not trying to support every possible theory of agent architecture.

RUNA exists to make building agent applications feel natural.

A developer should be able to start with an idea.

Build an agent.

Understand its behavior from its code.

Inspect what it did.

Evaluate whether it works.

And change it without rebuilding the infrastructure beneath it.

> **RUNA is an opinionated framework for building agent applications around a first-class execution primitive: the Run.**
