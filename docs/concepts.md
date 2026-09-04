# Runa Concepts

Runa keeps the developer-facing conceptual model deliberately small.

The core concepts are:

```text
Agent
Run
Context
State
Capability
```

A Run also produces and records:

```text
Events
Actions
Artifacts
Result
```

A Conversation carries state across Runs.

---

# Agent

An Agent is an application object that defines behavior and capabilities.

```python
class ResearchAgent(Agent):
    instructions = """
    Research questions carefully.
    Prefer reliable sources.
    """

    tools = [WebSearch]
```

The Agent answers:

> **What behavior does this part of the application provide?**

An Agent is a definition.

It is not an execution.

---

# Run

A Run is one execution of an Agent.

```python
run = ResearchAgent.run("Research fusion energy.")
```

The Run answers:

> **What happened when this Agent executed?**

A Run has an identity and lifecycle.

Conceptually:

```text
Run
├── Input
├── Goal
├── Context
├── State
├── Events
├── Actions
├── Artifacts
├── Result
└── Status
```

The Run is the execution boundary for the framework.

Persistence, background execution, observability, approval, retry behavior, and evaluation operate around the Run.

---

# Agent vs Run

This distinction is fundamental.

```text
ResearchAgent
    = behavior definition

Run #482
    = one execution of that behavior
```

One Agent can produce many Runs:

```text
ResearchAgent
    ├── Run #481
    ├── Run #482
    └── Run #483
```

A change to an Agent definition does not retroactively change historical Runs.

Durable Runs should retain enough identity and provenance to explain which Agent produced them.

---

# Context

Context is the information made available to an Agent while it makes decisions.

State is what the application or runtime owns.

Context is what the Agent is given.

Conceptually:

```text
Input
Conversation
Application resources
Policies
Run state
Environment
        ↓
     Context
        ↓
       Agent
```

Context may be assembled differently for different Runs.

Context should remain inspectable.

The goal is to understand what information was available when a decision was made.

```python
run.context.resources = [kb_article]
run.context.policies = ["no refunds over $500 without approval"]
```

In Runa's implementation, `Run.context` is a `Context` — the same
attribute-accessible container `RunState`/`ConversationState` use for
State (see below), populated explicitly by application code. Runa does not
auto-assemble it from Conversation/Resources/Policies/Run state; that
remains an application-level pattern, not framework machinery.

A non-empty `Context` does reach the Agent, though: it's rendered as a
second system message, right after `Agent.instructions`, before every Run
— a generic listing of whatever keys the application set, since Context is
free-form and no key name is treated specially. An empty `Context` (the
default) adds nothing to what the Agent sees.

---

# State

State is information that persists according to a defined lifetime.

Runa distinguishes:

## Run State

Belongs to one Run.

```python
run.state.sources
run.state.findings
```

## Conversation State

Spans multiple Runs.

```python
conversation.state.summary
conversation.state.preferences
```

## Application State

Belongs to the application domain.

```text
Customer
Order
ResearchProject
Ledger
```

Do not use one universal “memory” abstraction when the ownership and lifetime are different.

> **State has a lifetime.**

---

# Capability

A Capability is something an Agent is allowed to attempt.

Tools provide implementations of capabilities.

```text
Agent
  ↓
Capability
  ↓
Tool
```

Capabilities should be visible from the Agent definition.

In Runa's implementation, a `Tool` declared on `Agent.tools` *is* the
capability declaration — `Tool.tool_name()` already carries the identity
this diagram calls Capability. There is no separate `Capability` class
between Agent and Tool; one would only rename `Tool` without adding
behavior.

An Agent can also delegate to another Agent through a capability:

```python
ResearchAgent.as_tool()  # for a parent driven by Executor/run()
ResearchAgent.as_async_tool()  # for a parent driven by AsyncExecutor/run_async()
```

This keeps composition within the same programming model.

The delegated Agent's Run records the parent Run's id as `parent_run_id`,
so delegation lineage survives being persisted and read back later.

---

# Action

An Action is a specific attempted operation.

A Tool is an implementation.

A Capability is what the Agent may attempt.

An Action is a particular invocation.

```text
Capability
    ↓
Tool
    ↓
Action
```

For example:

```text
Capability: refund_customer
Tool: RefundCustomer
Action: refund(customer=123, amount=50)
```

An Action may require policy checks or approval before execution.

In Runa's implementation, `ToolCall` (`core/message.py`) is this invocation
record: `.attempts` counts how many times it's been tried, `.idempotent`
says whether retrying it is safe, and `.error` records what went wrong.
There is no separate `Action` class — `ToolCall` already carries what an
Action needs to be retried safely.

---

# Effect

An Effect is the consequence of an Action in the outside world.

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
Effect: refund successfully created
```

An Action and its Effect should not be treated as the same thing.

This distinction matters for retries, failures, idempotency, auditing, and approval.

In Runa's implementation, `ToolCall.effect: EffectStatus` (`NONE` /
`OBSERVED` / `UNKNOWN`) is this — a typed field on the same `ToolCall`
rather than a separate object, since an Action and its Effect share one
identity and lifecycle. A call that raises leaves its effect `UNKNOWN`, not
`NONE`: the exception doesn't say whether the side effect fired before it
was raised, which is exactly why `RetryStrategy` only retries a call whose
tool opts in with `idempotent = True`.

---

# Policy and Authority

Agents can make decisions.

The application determines what those decisions are allowed to do.

```text
Decision
    ↓
Capability
    ↓
Policy
    ↓
Approval, if required
    ↓
Action
    ↓
Effect
```

The principle is:

> **Intelligence does not imply authority.**

Use model intelligence for judgment.

Use application code for guarantees.

In Runa's implementation, `Agent.policies` declares a list of programmatic
allow/deny checks, run before a tool call can reach approval:

```python
def block_large_transfers(run, tool_call) -> bool:
    return tool_call.arguments.get("amount", 0) <= 10_000


class FinanceAgent(Agent):
    tools = [TransferFunds]
    policies = [block_large_transfers]
```

A Policy can veto a call outright — the Run fails without ever routing to
a human. This is deliberately separate from `requires_approval`, which
always defers to a human: Policy is for rules the application can decide
on its own; approval is for decisions that need a person.

---

# Event

An Event records a meaningful occurrence during a Run.

Examples (the full set is `EventType` in `core/event.py`):

```text
RunQueued
RunStarted
RunPaused
RunResumed
RunCompleted
RunFailed
RunCancelled
ModelCalled
ModelResponded
ToolCalled
ToolCompleted
ToolFailed
ApprovalRequired
PolicyDenied
ArtifactCreated
```

There is no separate `ActionProposed` event — `ToolCalled` already fires
before a tool executes, which is what that would have recorded.

The event history answers:

> **What happened?**

Observability should be derived from this execution history rather than maintained as a parallel execution system.

---

# Artifact

An Artifact is something produced by a Run.

Examples:

```text
Text
Structured Data
File
Citation Set
Plan
```

Artifacts are distinct from Actions.

A report is produced.

A transfer is performed.

A plan may be produced before any corresponding action occurs.

---

# Result

A Result is the final application-facing outcome of a Run.

A Run can produce several Artifacts and Actions while still having one final Result.

An Agent application therefore does not need to reduce its output to a single text response.

---

# Conversation

A Conversation is state that spans multiple Runs.

```text
Conversation
  ├── Run #1
  ├── Run #2
  └── Run #3
```

A Conversation does not execute anything.

It is state across executions.

The Run remains the fundamental execution boundary.

A Conversation is meant to be held across separate Runs, but not across
*concurrent* ones: two Runs racing against the same Conversation are not
merged — whichever finishes last silently overwrites the other's turn. See
architecture.md's Conversation section for what guarantee actually holds.

---

# Strategy

A Strategy controls how a Run advances.

It is a runtime mechanism, not normally the application's primary programming model.

```text
Agent
  ↓
Run
  ↓
Strategy
  ↓
Execution
```

Use the default strategy whenever possible.

Use custom Strategies when the execution loop itself needs to change shape.

Planning, reflection, ReAct, graph execution, and multi-agent patterns are not mandatory Runa concepts.

> **Standardize execution, not intelligence.**

---

# Lifecycle

A Run can move through different states:

```text
Created
  ↓
Queued
  ↓
Running
  ├── AwaitingApproval → Running (approved) or Cancelled/Failed (denied)
  └── Paused → Running
  ↓
Completed
Failed
Cancelled
```

This is `RunStatus` in `core/run.py`, exactly — there is no separate
`Waiting` status; a Run that's paused waiting on something external is
`Paused`, and one blocked on a human decision is `AwaitingApproval`.

A background Run, an approval-gated Run, and a synchronous Run are still Runs.

The programming model does not change.

---

# The Whole Model

The Runa mental model can be summarized as:

```text
Application
    │
    ├── Resources
    └── Policies
          │
          ▼
        Agent
          │
          │ defines behavior
          ▼
         Run
          │
     ┌────┼────┐
     │    │    │
 Context State Capabilities
          │
          ▼
       Execution
          │
     ┌────┼────┐
     │    │    │
   Events Actions Artifacts
          │
          ▼
        Result
```

The framework's center remains simple:

> **Agents define behavior. Runs define execution.**
