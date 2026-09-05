# The RUNA Doctrine

RUNA is an opinionated, integrated framework for building agent applications around the Run: the first-class unit of execution.

RUNA is inspired by the philosophy that made Rails effective: conventions over configuration, integrated systems over assembled stacks, strong defaults, beautiful code, and developer happiness.

But agent applications introduce a different kind of software. They combine ordinary application code with probabilistic decision-making, external capabilities, durable execution, and real-world consequences.

RUNA exists to make that complexity feel natural.

---

## 1. Optimize for Developer Happiness

Building an agent should begin with intent, not infrastructure.

The common path should be simple. Complexity should be available when the application needs it, but it should not be the price of getting started.

RUNA should let developers describe what an agent does without first assembling its runtime.

---

## 2. Convention Over Configuration

Agent applications contain recurring patterns.

Agents have capabilities. Runs have state. Executions produce events and artifacts. Runs can be persisted, resumed, evaluated, and observed.

Developers should not repeatedly configure these relationships.

RUNA uses conventions so that structure, names, and types carry meaning.

Explicit configuration should be reserved for decisions that are genuinely application-specific.

**Define the application once. Let the framework carry the conventions forward.**

---

## 3. The Run Is the Unit of Execution

An Agent defines behavior.

A Run represents one execution of that behavior.

The Run is the common boundary for lifecycle, state, events, actions, artifacts, persistence, background execution, approval, and evaluation.

A Run may be short or long, synchronous or asynchronous, complete or paused.

The execution model remains the same.

---

## 4. Agents Are Objects

Agents should be ordinary application objects with responsibilities, behavior, and capabilities.

Developers should not need to construct graphs to express simple agent behavior.

Graphs and workflows are useful when relationships or execution structure are the problem being modeled. They are not the default programming model.

**Agents define behavior. Runs define execution.**

---

## 5. Omakase Agent Infrastructure

Developers should not have to assemble an agent stack before they can build an application.

RUNA provides a coherent default environment for models, tools, runs, persistence, background execution, observability, approval, and evaluation.

The defaults are strong.

The system remains open.

---

## 6. State Has a Lifetime

Memory is not one thing.

RUNA distinguishes state by ownership and lifetime:

- Run state belongs to one execution.
- Conversation state spans related executions.
- Application state belongs to the application domain.

State should be explicit rather than hidden behind one universal memory abstraction.

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

The simplest agent should remain simple.

---

## 9. Behavior Must Be Observable and Evaluatable

Agent execution should answer two questions:

> **What happened?**

and:

> **Was it good?**

Events make execution observable.

Tests verify deterministic application invariants.

Evaluations measure agent behavior.

Observability and evaluation are part of development, not afterthoughts.

---

## 10. Provide Sharp Knives

Strong defaults should never become a prison.

Developers should be able to inspect Runs, access state and messages, invoke tools and models directly, override runtime behavior, and integrate external infrastructure.

The framework makes the common path easy.

The underlying system remains accessible.

---

# The Runa Standard

Before adding a feature to the core framework, ask:

- Does it make the common case simpler?
- Does it follow an existing convention?
- Does it make agent behavior easier to understand?
- Does it belong naturally to a Run?
- Does it make capabilities and authority clearer?
- Does it improve observability or evaluation?
- Can Runa provide a strong default?
- Does it preserve an escape hatch?

If not, it may not belong in the core.

---

# In One Sentence

> **RUNA is an opinionated, integrated framework for building agent applications around the Run: the first-class unit of execution.**
