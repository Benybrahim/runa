# Runa Concepts

Runa keeps the developer-facing conceptual model deliberately small.

Runa follows the Agent-Run-Execution (ARE) pattern: Agent declares behavior, Execution progresses it, and Run persists what happened.

The core concepts are:

```text
Agent
Execution
Run
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

# The Agent-Run-Execution (ARE) Pattern

ARE is the pattern Runa is built around. It divides an agent application
into three layers, each with a specific responsibility:

```text
Agent
  ↓ declares behavior
Execution
  ↓ progresses it
Run
  ↓ persists it
```

## Why ARE

Agent applications combine ordinary application code with probabilistic
decision-making, external capabilities, durable execution, and real-world
consequences. Separating what an agent does (Agent) from how it gets done
right now (Execution) from what happened (Run) keeps that complexity
tractable: persistence, background execution, approval, observability, and
evaluation can all be built around the Run without reaching into how an
Agent is defined or how Execution is implemented.

One Agent can produce many Runs. Changing an Agent's definition does not
retroactively change historical Runs.

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

# Execution

Execution is what progresses an Agent's behavior: calling the model, invoking tools, applying policy, and deciding what happens next.

```python
run = ResearchAgent.run("Research fusion energy.")
```

Calling `Agent.run()` is what starts Execution. In Runa's implementation, Execution is the `Executor`/`AsyncExecutor` driving a `Strategy`; most applications never touch either directly.

Execution answers:

> **What is happening right now, and what happens next?**

Execution is a process, not a record. It reads an Agent's declaration and a Run's accumulated state, and it writes new state, events, and actions back onto that Run as it goes.

---

# Run

A Run is the persisted record of one Agent invocation: what Execution has done so far, and what it produced.

The Run answers:

> **What happened when this Agent executed?**

A Run has an identity and lifecycle.

Conceptually:

```text
Run
├── Input
├── Goal
├── State
├── Messages
├── Events
├── Actions
├── Artifacts
├── Result
└── Status
```

The Run is where Execution's progress is persisted, which makes it the common boundary for the rest of the framework.

Persistence, background execution, observability, approval, retry behavior, and evaluation operate around the Run.

---

# Agent, Execution, and Run

This distinction is fundamental.

```text
ResearchAgent
    = behavior declaration

Execution
    = the process advancing Run #482 right now

Run #482
    = the persisted record of that invocation
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

# Model Context

What a model call sees is not a persisted object. It is a projection
Execution builds from `Agent.instructions`, the Run's accumulated
`Messages`, and whatever `State` the application chooses to surface, at
the moment a model call happens.

```text
Instructions
Messages
Selected State
        ↓
   Model input
        ↓
      Agent
```

> **Model context is a projection of the Run for a particular model call. RunState is the persistent execution state it is drawn from.**

Runa does not keep a separate `Context` type alongside `State`. The two
would share the same free-form, attribute-accessible shape (see below);
the only thing a distinct type bought was auto-rendering a whole container
into a system message before every Run, which does not scale as a
default. State can hold working data the model should not see
(accumulated findings, internal bookkeeping); surfacing all of it
automatically means the framework would need an allowlist/denylist
convention to claw that back. Runa leaves the selection explicit instead.

In Runa's implementation, `Agent.before_run(run)` and `Agent.plan(run)`
are where an application does this: read whatever `run.state` (or
`run.conversation.state`) is relevant, and call `run.add_message(...)` to
put it in front of the model, in whatever shape the prompt needs:

```python
class SupportAgent(Agent):
    def before_run(self, run):
        if run.state.resources:
            run.add_message(
                Message(
                    role=Role.SYSTEM,
                    content=f"Resources: {run.state.resources}",
                )
            )
```

`before_run`/`plan` are the same hooks Execution already calls once,
right after seeding a Run's instructions and input message and before the
step loop starts, so this needs no new framework machinery. What the
model actually saw stays inspectable the same way everything else does:
the messages these hooks add are ordinary Run messages, in `run.messages`
alongside every other turn.

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
capability declaration: `Tool.tool_name()` already carries the identity
this diagram calls Capability. There is no separate `Capability` class
between Agent and Tool; one would only rename `Tool` without adding
behavior.

An Agent can also delegate to another Agent, declared separately from `tools`
so a reader can tell "capabilities this agent uses" from "agents this agent
delegates to" at a glance:

```python
class LeadAgent(Agent):
    delegations = [ResearchAgent]
```

This keeps composition within the same programming model: a delegation still
resolves to an ordinary Tool internally, so it reuses `DefaultStrategy`'s
existing tool-use loop, no new Strategy needed.

Every delegation's schema accepts `input` plus an optional `transfer` flag,
and the model decides per call which outcome it wants:

* **Return** (the default, `transfer` absent or `false`) — the delegated
  Agent runs to completion in its own nested Run, and its result comes back
  as a tool result. The nested Run's `parent_run_id` records the parent
  Run's id, so delegation lineage survives being persisted and read back
  later.
* **Transfer** (`transfer: true`) — no nested Run is created. The delegated
  Agent instead becomes the one driving the *same* Run for the rest of its
  lifetime: its own instructions take over, and `Run.active_agent_name`
  updates to reflect the handoff (`Run.agent_name` keeps recording who the
  Run was originally given to). Use this for a handoff, e.g. a triage agent
  passing a conversation to a specialist.

`DelegateAgent`/`AsyncDelegateAgent` are the two ways to override a
delegation's `executor` (e.g. for tests, or a specific provider):
`AsyncDelegateAgent` additionally runs the Return outcome through
`AsyncExecutor` directly, so several delegates called in one model turn run
as genuine concurrent async I/O rather than one thread each. Neither matters
for Transfer, which never spawns a nested Run in the first place.

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
There is no separate `Action` class: `ToolCall` already carries what an
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
`OBSERVED` / `UNKNOWN`) is this: a typed field on the same `ToolCall`
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

A Policy can veto a call outright: the Run fails without ever routing to
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

There is no separate `ActionProposed` event: `ToolCalled` already fires
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
merged: whichever finishes last silently overwrites the other's turn. See
[Sharing State Across Runs](guides.md#sharing-state-across-runs) for the
pattern this implies for concurrent work.

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

This is `RunStatus` in `core/run.py`, exactly; there is no separate
`Waiting` status; a Run that's paused waiting on something external is
`Paused`, and one blocked on a human decision is `AwaitingApproval`.

A background Run, an approval-gated Run, and a synchronous Run are still Runs.

The programming model does not change.

---

# Persistence

Persistence makes a Run or a Conversation outlive the process that created it.

```text
Run / Conversation
      ↓
    Store
      ↓
 later process
```

A store should be swappable without changing application code:
`InMemoryRunStore`/`SQLiteRunStore` satisfy the same `RunStore` protocol,
and `InMemoryConversationStore`/`SQLiteConversationStore` do the same for
`ConversationStore`.

Persistence should not become a second source of execution truth. What a
store holds is a snapshot of the Run or Conversation, not a parallel record
of what happened.

See [Running in the Background](guides.md#running-in-the-background) and
[Persisting a Conversation](guides.md#persisting-a-conversation) for the
patterns.

---

# Background Execution

Background execution does not introduce a second kind of work.

```python
ResearchAgent.run(...)
ResearchAgent.run_later(...)
```

Both produce the same conceptual Run. The difference is when and where it
advances: `run()` progresses it immediately; `run_later()` hands it to a
Queue instead.

A Queue is infrastructure for scheduling execution. The Run remains the
unit of work, whether it's driven inline or picked up by a worker later.

See [Running in the Background](guides.md#running-in-the-background) for
the pattern, including crash recovery.

---

# Observability

Observability is derived from a Run's event history, not maintained as a
parallel record.

```text
Execution → Events → Timeline / Notifications / Inspection
```

The question observability answers is the same one the Event section above
asks:

> **What happened?**

A subscriber watching a Run live should not be able to affect its
execution: an observer that raises should degrade to a missed
notification, not a failed or crashed Run.

See [Inspecting Runs](guides.md#inspecting-runs) for the pattern.

---

# Evaluation

Evaluation measures probabilistic Agent behavior; tests verify
deterministic invariants.

```text
Production Agent
      ↓
     Run
      ├── inspect  (tests)
      └── evaluate (evaluations)
```

Both operate on the same Agent and Run semantics used in production.
There is no separate execution path built solely for evaluation.

See [Evaluating Behavior](guides.md#evaluating-behavior) for the pattern.

---

# Approval

Approval is a Run lifecycle transition, not a separate workflow model:

```text
Running → AwaitingApproval → Approved → Running
                            → Denied   → Failed / Cancelled
```

Approval always defers to a human. [Policy](#policy-and-authority) is the
earlier, programmatic check for rules the application can decide on its
own; a Policy denial fails the Run before it ever reaches approval.

See [Adding Human Approval](guides.md#adding-human-approval) for the
pattern.

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
          │ declares behavior
          ▼
      Execution
          │
       ┌──┴──┐
       │     │
     State Capabilities
          │
          ▼
         Run
          │
     ┌────┼────┐
     │    │    │
   Events Actions Artifacts
          │
          ▼
        Result
```

The framework's center remains simple:

> **Agents declare behavior. Execution progresses it. Runs persist it.**
