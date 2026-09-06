# Runa Concepts

Runa has a small conceptual model.

At its center:

> **Agents declare behavior. Execution progresses it. Runs record what happened.**

---

# Core Model

## Agent, Execution, and Run

Runa follows the **Agent–Run–Execution (ARE)** pattern.

```text
Agent
  ↓ declares behavior
Execution
  ↓ progresses behavior
Run
  ↓ records what happened
```

Each answers a different question:

```text
Agent     → What can this application do?
Execution → What happens next?
Run       → What happened?
```

---

## Agent

An Agent defines behavior.

```python
class ResearchAgent(Agent):
    instructions = "Research the user's question."

    tools = [WebSearch]
    delegations = [AnalysisAgent]
```

An Agent is a definition.

It is not an invocation.

One Agent can produce many Runs.

---

## Execution

Execution progresses an Agent through a Run.

It observes the current Run, decides what happens next, performs the work, and records the result.

```text
Observe
  ↓
Decide
  ↓
Act
  ↓
Record
  ↓
Repeat
```

Runa exposes the same execution in different forms:

```text
run()         execute asynchronously
run_sync()    execute synchronously
run_stream()  execute while streaming output
run_later()   schedule execution for later
```

These are different ways of progressing a Run.

They are not different Agent models.

---

## Run

A Run is the record of one Agent invocation.

```text
Run
├── Input
├── State
├── Messages
├── Events
├── Actions
├── Artifacts
├── Result
└── Status
```

Execution changes the Run as work progresses.

The Run is the fundamental execution boundary.

---

# What an Agent Can Do

## Tools and Capabilities

A Tool is something an Agent can use.

```python
class ResearchAgent(Agent):
    tools = [WebSearch]
```

Conceptually, a Tool represents a capability available to the Agent.

Runa does not need a separate Capability object.

The Tool declaration is the capability declaration.

---

## Actions

An Action is a particular use of a Tool.

```text
Tool
  ↓
Action
```

For example:

```text
Tool: RefundCustomer

Action:
refund(customer=123, amount=50)
```

A Tool defines what can be done.

An Action records an attempt to do it.

---

## Effects

An Effect is what an Action causes outside the system.

```text
Decision
  ↓
Action
  ↓
Effect
```

For example:

```text
Action: refund customer 123

Effect: refund created
```

An Action is an attempt.

An Effect is its consequence.

Keeping them separate matters when execution fails or is retried.

---

## Delegation

An Agent can delegate work to another Agent.

```python
class LeadAgent(Agent):
    delegations = [ResearchAgent]
```

Delegation is different from ordinary tool use because it invokes another Agent's behavior.

A delegation can:

### Return

The delegated Agent performs work and returns a result.

```text
Lead Agent
    ↓
Delegate
    ↓
Result
    ↓
Lead Agent continues
```

### Transfer

The delegated Agent takes over the Run.

```text
Lead Agent
    ↓
Transfer
    ↓
Specialist Agent
    ↓
continues the Run
```

Use **Return** when another Agent performs part of the work.

Use **Transfer** when responsibility for the Run moves to another Agent.

---

# What a Run Contains

## State

State is information with a defined lifetime.

Runa distinguishes three lifetimes.

### Run State

Belongs to one Run.

```python
run.state.sources
run.state.findings
```

### Conversation State

Spans multiple Runs.

```python
conversation.state.summary
conversation.state.preferences
```

### Domain State

Belongs to the application itself.

```text
Customer
Order
ResearchProject
Ledger
```

> **State has a lifetime.**

---

## Events

An Event records something meaningful that happened during a Run.

```text
RunStarted
ModelCalled
ToolCalled
ToolSucceeded
ArtifactCreated
RunCompleted
```

Events answer:

> **What happened?**

They provide the history used for inspection and observability.

---

## Artifacts

An Artifact is something produced by a Run.

```text
TextArtifact
DataArtifact
FileArtifact
```

Applications can define their own Artifact types.

```python
class ResearchArtifact(Artifact):
    citations: list[Citation]
```

An Artifact is something the Run **produced**.

An Action is something the Run **did**.

---

## Result

A Result is the final application-facing outcome of a Run.

A Run may perform many Actions and produce many Artifacts.

It still has one final Result.

---

# Control and Authority

## Policy

Agents make decisions.

The application determines what those decisions are allowed to do.

```text
Decision
  ↓
Policy
  ↓
Action
```

A Policy is a programmatic rule.

It can allow or deny an Action.

> **Intelligence does not imply authority.**

Use the model for judgment.

Use application code for guarantees.

---

## Approval

Some Actions require a human decision.

```text
Decision
  ↓
Policy
  ↓
Approval
  ↓
Action
```

Policy and approval answer different questions:

```text
Policy   → Can the application decide this?
Approval → Must a person decide this?
```

Approval is part of the Run's lifecycle.

It does not create a separate execution model.

---

## Lifecycle

A Run progresses through a lifecycle.

```text
Created
  ↓
Queued
  ↓
Running
  ├── Paused
  └── Awaiting Approval
  ↓
Completed
Failed
Cancelled
```

Background execution and approval do not create different kinds of Runs.

They are different states of the same execution model.

---

# Runs Across Time

## Conversation

A Conversation carries state across Runs.

```text
Conversation
├── Run #1
├── Run #2
└── Run #3
```

A Conversation does not execute anything.

It provides continuity between Runs.

The Run remains the execution boundary.

---

# Infrastructure

## Persistence

Persistence allows a Run or Conversation to outlive the process that created it.

```text
Run / Conversation
       ↓
      Store
       ↓
later process
```

A Store preserves state.

It does not become a second source of execution truth.

The Run remains the record of what happened.

---

## Background Execution

Background execution changes when and where a Run progresses.

It does not create a different kind of work.

```text
Agent.run(...)
Agent.run_later(...)
```

Both operate on the same conceptual Run.

The Queue is scheduling infrastructure.

The Run remains the unit of work.

---

## Observability

Observability is derived from what a Run records.

```text
Execution
    ↓
Events
    ↓
Inspection
Timeline
Notifications
```

Observers should observe execution without controlling it.

---

## Evaluation

Evaluation measures Agent behavior.

Tests verify deterministic behavior.

Both operate on the same Agent and Run model used in production.

There is no separate execution model for evaluation.

---

# The Whole Model

```text
Application
    │
    ├── Domain State
    └── Policies
          │
          ▼
        Agent
          │
          │ declares behavior
          ▼
      Execution
          │
          │ progresses
          ▼
         Run
          │
     ┌────┼────┐
     │    │    │
   State Events Actions
          │
     ┌────┴────┐
     │         │
Artifacts    Result
```

The model remains simple:

> **Agent declares behavior. Execution progresses it. Run records what happened.**
