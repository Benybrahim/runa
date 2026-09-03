# From Rails to Runa

Runa is inspired by Rails.

Not because agent applications need a Rails-shaped vocabulary, but because Rails demonstrated a powerful way to design application frameworks:

> Make common application problems feel native to the framework.

Rails reduced configuration, integrated common infrastructure, established conventions, and optimized for the happiness of the developer.

Runa applies those ideas to a different kind of application.

Agent applications introduce probabilistic decision-making, autonomous execution, capabilities, and interactions with the outside world. Their fundamental problems are different.

The goal is therefore not to reproduce Rails.

The goal is to carry its philosophy forward.

---

# The Core Analogy

The simplest mapping is:

```text
Rails                              Runa

Web application                    Agent application

Request                             Run

Request lifecycle                   Run lifecycle

Application code                   Agent behavior

Session state                       Conversation state

Application / domain state          Application / domain state

Background Job                      Background Run

Response                            Result / Artifacts

Instrumentation                     Run Events

Tests                               Tests + Evaluations

Generators                          Agent / Tool Generators
```

The most important relationship is:

> **The Request is to Rails what the Run is to Runa.**

A request gives a web application a unit of work.

A Run gives an agent application a unit of execution.

The Run is broader than a request. It may continue asynchronously, pause, wait, require approval, retry, resume, and produce multiple outputs.

The analogy is therefore about **the role of the abstraction**, not identical behavior.

---

# 1. Convention Over Configuration

Rails made developers specify application intent rather than repeatedly configure framework machinery.

Runa applies the same principle to agent development.

A developer should be able to define:

```python
class ResearchAgent(Agent):
    instructions = "Research carefully."
    tools = [WebSearch]
```

without manually assembling the execution machinery around it.

The framework can infer and provide:

* execution conventions
* tool integration
* state handling
* event recording
* persistence
* background execution
* evaluation

The deeper principle is:

> **Developers should describe the application; the framework should carry the conventions.**

For Runa, this could be described as:

> **Convention over orchestration.**

The problem being reduced is not only configuration. It is the repeated construction of agent execution machinery.

---

# 2. The Rails Request Becomes the Runa Run

Rails organizes web applications around the request lifecycle.

Runa organizes agent applications around the Run lifecycle.

```text
Rails

Request
  ↓
Application code
  ↓
Response
```

```text
Runa

Run
  ↓
Agent execution
  ↓
Result / Effects
```

A Run provides a common execution boundary for concerns that would otherwise become disconnected systems:

```text
Run
├── state
├── messages
├── events
├── actions
├── artifacts
├── result
└── lifecycle
```

Persistence, background execution, approval, observability, and evaluation operate on that same Run.

This is one of the central architectural ideas of Runa.

---

# 3. Application Objects

Rails encourages developers to model applications using ordinary objects.

Runa does the same.

An Agent is an application object.

It has:

* a responsibility
* behavior
* capabilities
* configuration
* lifecycle behavior

The developer should be able to understand an Agent from its definition.

This does not mean everything in a Runa application becomes an Agent.

A Runa application can still contain ordinary domain objects:

```text
Customer
Order
Project
Document
Ledger
```

Agents add intelligence to an application.

They do not replace application architecture.

---

# 4. Active Record and the Runa Lesson

Runa does not need a direct equivalent of Active Record.

The lesson is more important than the mapping.

Rails made persistence feel like a native part of application programming rather than a separate infrastructure problem.

Runa aims to do something similar with execution.

```text
Rails

Application
    ↓
Domain objects
    ↓
Active Record
    ↓
Persistence
```

```text
Runa

Application
    ↓
Agent
    ↓
Run
    ↓
Execution infrastructure
```

The Run should make execution feel native to application development.

Developers should not need to construct an execution platform before they can execute application behavior.

---

# 5. Background Jobs Become Background Runs

Rails treats background work as a variation of ordinary application work.

Runa should do the same for agent execution.

```python
ResearchAgent.run(...)
```

and:

```python
ResearchAgent.run_later(...)
```

should produce the same conceptual object:

> **A Run.**

The difference is when and where the Run advances.

This means background execution does not require a second programming model.

---

# 6. Session Becomes Conversation State

Rails applications often distinguish request-local state from session state.

Runa needs a similar distinction.

```text
Run State
    ↓
one execution

Conversation State
    ↓
multiple related Runs

Application State
    ↓
the application domain
```

The important difference is that Runa deliberately avoids treating all persistent agent information as “memory.”

> **State has a lifetime.**

Conversation is state across Runs, not the execution boundary itself.

---

# 7. Response Becomes Outcome

A web request normally produces a response.

An agent Run can produce much more:

```text
Text
Structured Data
File
Citation Set
Plan
```

These are artifacts and results of execution.

An agent application therefore should not be reduced to:

```text
prompt → text
```

The more useful abstraction is:

```text
Run
  ↓
Outcome
  ├── Result
  ├── Artifacts
  └── Effects
```

The framework should treat the outcome as application data.

---

# 8. Testing Becomes Testing + Evaluation

Traditional application tests verify deterministic behavior.

Agent applications need that too.

But probabilistic behavior introduces another question:

> How good was the behavior?

Runa therefore separates:

```text
Tests
    verify application invariants

Evaluations
    measure agent behavior
```

A test may verify:

```python
assert run.completed
assert ticket.created
```

An evaluation may measure:

```python
expect(run).to_be_factual()
expect(run).to_meet_the_goal()
```

This is a Runa-specific extension of the Rails testing philosophy.

The framework should make both part of normal development.

---

# 9. Rails Instrumentation Becomes Run Events

Rails applications benefit from instrumentation around application activity.

Runa has an even more fundamental need because agent execution is often difficult to reconstruct from a final result.

A Run records meaningful events:

```text
Run Started
Model Called
Tool Called
Tool Completed
Action Proposed
Approval Requested
Artifact Created
Run Completed
```

The event history should be a natural consequence of execution.

Observability is therefore not a separate execution system.

> **The Run records what happened. Observability makes it understandable.**

---

# 10. Generators Encode Convention

Rails generators make conventional project structure easy to create.

Runa can do the same:

```text
runa new
runa generate agent
runa generate tool
runa generate evaluation
```

Generators are not merely productivity features.

They reinforce the framework's conventions.

A generated application should teach a developer how Runa applications are structured.

> **Structure carries meaning.**

---

# 11. Omakase

Rails is known for making strong default choices rather than presenting an endless menu of independent components.

Runa faces an even larger ecosystem of choices:

```text
models
providers
tools
memory
retrieval
queues
persistence
observability
evaluation
orchestration
```

Runa therefore adopts an omakase philosophy:

> **The framework makes the common decisions so developers can focus on the application decisions.**

The developer should be able to start with a coherent system and replace components only when there is a reason to do so.

---

# 12. Integrated Systems

Rails demonstrated the value of building an integrated application environment instead of merely combining compatible libraries.

Runa follows the same principle.

```text
Agent
  ↓
Run
  ├── Persistence
  ├── Background execution
  ├── Observability
  ├── Approval
  └── Evaluation
```

These systems understand the same execution model.

A tool call belongs to a Run.

A Run produces events.

A Run can be persisted.

A Run can be evaluated.

A Run can be resumed.

The value is in the relationships between the components.

> **Integration is a feature.**

---

# 13. No One Paradigm

Rails does not require every application to be structured around one programming paradigm.

Runa should similarly avoid prescribing one theory of intelligence.

An agent may:

* answer directly
* use tools
* plan
* delegate
* reflect
* use deterministic logic
* use probabilistic reasoning

Runa standardizes the execution lifecycle, not the thought process.

> **One lifecycle, many strategies.**

Graphs, workflows, planning systems, and multi-agent patterns remain available when they are useful.

They should not become mandatory application architecture.

---

# 14. Sharp Knives

Rails provides strong conventions without completely hiding the underlying system.

Runa should do the same.

Developers should be able to leave the happy path when necessary:

```text
inspect a Run
access messages
access state
invoke a tool directly
invoke a model directly
replace persistence
replace execution strategy
integrate external infrastructure
```

The framework provides conventions.

It does not become a prison.

> **Make the common path simple. Keep the underlying power accessible.**

---

# Where Runa Must Depart From Rails

The Rails analogy has limits.

Agent applications have properties web applications do not need to treat as foundational.

## Probabilistic behavior

A model may produce different decisions from the same input.

Runa therefore needs evaluations in addition to ordinary tests.

## Autonomous execution

A Run can continue without a request waiting synchronously for a response.

It may wait, retry, pause, resume, or run in the background.

## Capabilities and authority

An agent can decide what it wants to do.

That does not mean it is authorized to do it.

Runa therefore separates:

```text
Decision
    ↓
Capability
    ↓
Policy
    ↓
Approval
    ↓
Action
    ↓
Effect
```

## Context

Agent behavior depends heavily on what information is presented to the model.

Runa therefore treats Context as a distinct concept from State.

## Real-world effects

Agents may change external systems.

A proposed action, an executed action, and the resulting effect are not the same thing.

These concepts have no direct one-to-one Rails equivalent.

They are part of Runa's own ontology.

---

# Rails Gives Runa Its Temperament

The goal is not to turn every Rails concept into an agent concept.

Rails provides the design attitude:

```text
Developer happiness
Convention
Omakase
Integration
Beautiful code
Sharp knives
Progress
```

Agent development supplies the concepts that Runa must make native:

```text
Agent
Run
Context
State
Capability
Action
Effect
Event
Artifact
Evaluation
```

This distinction is important.

> **Rails provides the temperament. Agentics provides the ontology.**

Runa is the combination.

---

# The Result

Rails changed the way developers think about web applications.

It did not merely provide better libraries. It provided a coherent way to structure an application and made the common path feel obvious.

Runa aims to do the same for agent applications.

The developer should think primarily about:

```text
Agent → Run → Outcome
```

and rely on the framework for the machinery around that execution:

```text
state
tools
persistence
background execution
observability
approval
evaluation
```

The result is not a framework that hides complexity.

It is a framework that puts complexity in the right place.

> **Runa makes agent development feel like application development.**
