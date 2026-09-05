# The RUNA Doctrine

RUNA is an opinionated, integrated framework for building agent applications.

Its architecture is built around three core concepts: **Agent, Execution, and Run**.

Agents declare behavior. Execution progresses that behavior. Runs persist what happened.

**The Run is the core unit.**

RUNA is inspired by the philosophy that made Rails effective: conventions over configuration, integrated systems over assembled stacks, strong defaults, beautiful code, and developer happiness.

But agent applications introduce a different kind of software. They combine ordinary application code with probabilistic decision-making, external capabilities, durable execution, and real-world consequences.

RUNA exists to make that complexity feel natural.

---

## 1. Agent, Execution, and Run

RUNA organizes an agent application around three core concepts, each with a distinct responsibility.

An **Agent** declares behavior: what it is, what it can do, and how it should behave.

**Execution** is the runtime that progresses that behavior through time: calling models, invoking tools, applying policy, and determining what happens next.

A **Run** persists what happened: its identity, lifecycle, state, events, actions, artifacts, and result.

The Run is the common boundary for persistence, background execution, approval, observability, and evaluation, because it is where Execution's progress is recorded.

A Run may be short or long, synchronous or asynchronous, complete or paused.

The execution model remains the same.

**Agents declare behavior. Execution progresses it. Runs persist what happened.**

---

## 2. Agents Are Objects

Agents should be ordinary application objects with responsibilities, behavior, and capabilities.

Developers should not need to construct graphs to express ordinary agent behavior.

Graphs and workflows are useful when execution structure itself is the problem being modeled. They are not the default programming model.

**Objects before graphs.**

---

## 3. Optimize for Developer Happiness

Building an agent should begin with intent, not infrastructure.

The common path should be simple. Complexity should be available when the application needs it, but it should not be the price of getting started.

RUNA should let developers describe what an agent does without first assembling its runtime.

**Intent before infrastructure.**

---

## 4. Convention Over Configuration

Agent applications contain recurring structure.

Agents have capabilities. Runs have state. Executions produce events and artifacts. Runs can be persisted, resumed, evaluated, and observed.

Developers should not repeatedly configure these relationships.

RUNA uses conventions so that structure, names, and types carry meaning.

Explicit configuration should be reserved for decisions that are genuinely application-specific.

**Define the application once. Let the framework carry the conventions forward.**

---

## 5. Omakase Agent Infrastructure

Developers should not have to assemble an agent stack before they can build an application.

RUNA provides a coherent environment for models, tools, runs, persistence, background execution, observability, approval, and evaluation.

The defaults are strong.

The system remains open.

Omakase does not mean that every application must use every component. It means that when applications need these capabilities, they work together by default rather than requiring developers to assemble and integrate them themselves.

**Integrated before assembled.**

---

## 6. State Has an Owner and a Lifetime

Memory is not one thing.

State has an owner and a lifetime.

RUNA distinguishes state accordingly:

* **Run state** belongs to one Run.
* **Conversation state** spans related Runs.
* **Application state** belongs to the application's domain.

State should be explicit rather than hidden behind one universal memory abstraction.

**State has an owner and a lifetime.**

---

## 7. Capabilities Do Not Imply Authority

Agents can reason about what should happen.

The application determines what the agent is allowed to do.

Capabilities, policies, permissions, and approvals make that boundary explicit.

**Intelligence does not imply authority.**

Important effects on the world should pass through explicit application boundaries.

---

## 8. Standardize Execution, Not Intelligence

RUNA provides a consistent execution lifecycle without prescribing one theory of agent behavior.

Agents may use tools, planning, delegation, reflection, deterministic logic, or probabilistic reasoning.

Those are strategies, not requirements.

RUNA standardizes the software engineering around intelligence, not intelligence itself.

The simplest agent should remain simple.

**Standard runtime. Open behavior.**

---

## 9. Behavior Must Be Observable and Evaluatable

Agent execution should answer two questions:

> **What happened?**

and:

> **Was it good?**

Runs and events make execution observable.

Tests verify deterministic application invariants.

Evaluations measure agent behavior.

Observability and evaluation are part of development, not afterthoughts.

---

## 10. Provide Sharp Knives

Strong defaults should never become a prison.

Developers should be able to inspect Runs, access state and messages, invoke tools and models directly, override runtime behavior, and integrate external infrastructure.

The framework makes the common path easy.

The underlying system remains accessible.

**Strong defaults. Clear escape hatches.**

---

# The Runa Standard

Before adding a feature to the core framework, ask:

* Does it make the common case simpler?
* Does it follow an existing convention?
* Does it make agent behavior easier to understand?
* Does it belong naturally to an Agent, Execution, or Run?
* Does it make state ownership or lifetime clearer?
* Does it make capabilities and authority clearer?
* Does it improve observability or evaluation?
* Can Runa provide a strong default?
* Does it preserve an escape hatch?

If not, it may not belong in the core.

---

# In One Sentence

> **RUNA is an opinionated, integrated framework for agent applications, built around the Agent-Execution-Run architecture: Agents declare behavior, Execution progresses it, and Runs persist what happened. The Run is the core unit.**
