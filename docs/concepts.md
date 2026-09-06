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
## The Agent-Run-Execution (ARE) Pattern

ARE is the core pattern Runa is built around.

```text id="hvbq6c"
Agent
  ↓ defines behavior
Execution
  ↓ progresses it
Run
  ↓ persists what happened
```

The three concepts answer different questions:

```text id="s7hndc"
Agent     → What behavior does this application provide?
Execution → What is happening now, and what happens next?
Run       → What happened?
```

---

### Agent

An Agent is an application object that defines behavior and capabilities.

```python id="vds2ai"
class MyAgent(Agent):
    instructions = """
    My Agent instruction
    """

    tools = [WebSearch]
    delegations = [MyAgent2, MyAgent3]
```

An Agent is a definition, not an invocation.

---

### Execution

Execution is the process that progresses an Agent's behavior.

```python id="e7z1q5"
run = ResearchAgent.run_sync("Research fusion energy.")
```

It reads the Agent's declaration and the current Run, calls the model, invokes tools, applies policy, decides what happens next, and records its progress on the Run.

```text id="kbyazb"
Agent + Run
     ↓
 Execution
     ↓
 Decide
     ↓
 Act
     ↓
 Update Run
     ↓
 Repeat
```

`Agent`'s Execution API is one Execution, observed four ways, not four
different behaviors:

```text
run()         → the native async execution path
run_sync()    → a synchronous adapter over run()
run_stream()  → execute now, streaming output
run_later()   → enqueue for later/background execution
```

`run()`/`run_sync()`/`run_stream()` all drive the Run to its next pause
point before returning; they differ in whether the caller awaits, blocks,
or observes output incrementally. `run_sync()` isn't a second execution
model, it drives the exact same `Executor` loop as `run()` via
`asyncio.run()`, so it can't be called from inside a running event loop.
`run_later()` is the one that doesn't drive to a pause point synchronously
at all: it hands the Run to a Queue and returns immediately, so it is the
only member of the four that answers "when," not just "how." See
[Background Execution](#background-execution).

---

### Run

A Run is the persisted record of one Agent invocation and its execution.

```text id="xqhh7s"
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

A Run has its own identity and lifecycle.

---

### Relationship

One Agent can produce many Runs:

```text id="h8umbl"
ResearchAgent
    ├── Run #481
    ├── Run #482
    └── Run #483
```

For each invocation, Execution progresses that Agent's behavior and persists what happens to its Run.

Changing an Agent's definition does not retroactively change historical Runs. Durable Runs should retain enough identity and provenance to explain which Agent definition produced them.

---

### Why ARE

Agent applications combine probabilistic decisions, application code, external capabilities, persistence, and real-world side effects.

ARE keeps these concerns separate:

* **Agent** defines behavior.
* **Execution** progresses behavior.
* **Run** persists what happened.

**Because progress is recorded on the Run, persistence, background execution, approval, observability, retry behavior, and evaluation can operate around the Run without coupling themselves to Agent definitions or Execution internals.**

---

## State

State is information that persists according to a defined lifetime.

Runa distinguishes:

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

### Application State

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

Pass `DelegateAgent(SomeAgent, executor=...)` to override a delegation's
`executor` directly (e.g. for tests, or a specific provider); its `call()`
awaits the Return outcome's `Executor` directly, so several delegates
called in one model turn run as genuine concurrent async I/O rather than
one thread each. Doesn't matter for Transfer, which never spawns a nested
Run in the first place.

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

Runa has no separate `guardrails` concept. A guardrail is a rule an
application wants enforced around model behavior, which is exactly what a
Policy is; introducing a second name for the same idea would only add a
second place to look.

`requires_approval` belongs to the Tool being called, not the Agent
calling it: set it on the Tool (`class TransferFunds(Tool):
requires_approval = True`, or `@tool(requires_approval=True)`), and every
Agent that declares that Tool inherits the gate. Approval is a property
of the action, not a per-agent override list.

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

Every Runa Agent uses the same control loop: a ReAct-style cycle of
observe, decide, act, and repeat.

```text
Agent
  ↓ declares capabilities + constraints
Execution
  ↓
ReAct strategy
  ↓
Action
  ├── Tool
  ├── Delegate
  ├── State update
  └── Finish
  ↓
Run updated
  ↓
Repeat
```

> **Every Runa Agent uses a ReAct-style execution loop: observe state,
> decide an action, execute it, observe the result, and repeat until
> completion.**

Applications do not choose between a planner, an orchestrator, a
reflection loop, and ReAct. There is one loop. A Strategy is what
implements it, and Strategy is a runtime mechanism, not normally the
application's primary programming model, and not a field on `Agent`:
choosing between execution strategies is not part of the normal Agent
configuration surface.

In Runa's implementation, `DefaultStrategy` (`runtime/strategy.py`) *is*
this loop: given a Run, it decides `CallModel`, `CallTool`, `Complete`, or
`Fail` from what has already happened, the Executor performs that
decision, and the cycle repeats. Reach for a custom Strategy, passed
explicitly to `Executor`, only when the loop's shape itself must change:

```python
executor = Executor(provider, strategy=CustomStrategy())
```

This is an escape hatch for the rare case that needs it, not a normal
Agent configuration knob.

Use Agent lifecycle hooks (`before_run`/`after_run`) for behavior around
the loop; reach for a custom Strategy only when the loop itself must work
differently. See [Choosing Between Agent Hooks and
Strategy](guides.md#choosing-between-agent-hooks-and-strategy).

The canonical principle:

> **Agent declares. ReAct decides. Execution performs. Run records.**

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
