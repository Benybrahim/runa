# Runa Guides

This document contains practical patterns for common Runa applications.

The examples assume the normal Runa model:

```text
Agent → Run → Outcome
```

---

# Building a Tool

Start with the smallest possible tool.

```python
from runa import Tool


class WebSearch(Tool):
    def call(self, query: str):
        return search_web(query)
```

Then declare it on an Agent:

```python
class ResearchAgent(Agent):
    instructions = """
    Research carefully.
    Prefer reliable sources.
    """

    tools = [WebSearch]
```

Keep the Agent responsible for behavior and the Tool responsible for the external operation.

---

# Structuring Application State

Keep domain state in ordinary application objects.

```python
class Customer:
    def __init__(self, name, plan):
        self.name = name
        self.plan = plan
```

Use Run State for temporary execution information:

```python
run.state.findings = []
run.state.sources = []
```

Use Conversation State for information that spans multiple Runs.

Do not turn durable application concepts into “agent memory” merely because an Agent uses them.

---

# Sharing State Across Runs

Create a Conversation when multiple Runs belong to the same interaction:

```python
conversation = Conversation()

SupportAgent.run(
    "My invoice is wrong.",
    conversation=conversation,
)

SupportAgent.run(
    "Can you explain the correction?",
    conversation=conversation,
)
```

Conversation state survives across these executions.

Run state does not.

---

# Running in the Background

Use `run_later()` when work should not execute as part of the immediate call:

```python
run = ResearchAgent.run_later("Produce a detailed report.")
```

The returned object represents the same conceptual unit of work as `run()`.

For durable background execution, configure a persistent Run store and an appropriate Queue.

Do not create a separate “job object” in application code just because execution happens later.

---

# Inspecting Runs

A Run records execution events.

Use the Run timeline or CLI tooling to inspect execution:

```bash
runa runs show <id>
```

A useful inspection question is:

```text
What happened?
```

Look for:

- model calls
- tool calls
- state changes
- approvals
- retries
- artifacts
- failures
- completion

The event history should be useful during development, not only after deployment.

---

# Evaluating Behavior

Use ordinary tests for deterministic application invariants:

```python
def test_research_completes():
    run = ResearchAgent.run("Research fusion energy.")
    assert run.completed
```

Use evaluations for probabilistic behavior:

```python
cases = [
    "Research fusion energy.",
    "Compare the leading approaches.",
]

expect(run).to_be_factual()
expect(run).to_meet_the_goal()
```

Keep evaluation on the same Agent and Run path used in production.

Avoid creating a special mock architecture for evaluation unless a test specifically needs one.

---

# Adding Human Approval

Declare approval requirements at the Agent boundary:

```python
class FinanceAgent(Agent):
    tools = [TransferFunds]

    requires_approval = [
        TransferFunds,
    ]
```

When execution reaches that action:

```text
Running
   ↓
AwaitingApproval
   ↓
Approved
   ↓
Running
```

The Run remains the same execution.

Approval changes the lifecycle; it does not create a separate workflow model.

---

# Delegating to Another Agent

Compose Agents through capabilities:

```python
class ResearchAgent(Agent):
    tools = [WebSearch]


class ReportAgent(Agent):
    tools = [ResearchAgent.as_tool()]
```

The delegated Agent creates its own Run.

This keeps agent composition explicit while avoiding a separate multi-agent programming model.

Use delegation when the child Agent represents a meaningful responsibility.

Do not split an Agent into many sub-agents merely because the framework supports delegation.

---

# Handling Long-Running Work

Long-running work should still be expressed as a Run.

The Run may:

```text
start
↓
execute
↓
wait
↓
resume
↓
complete
```

Design the application around the lifecycle rather than around the worker implementation.

The Queue, process, thread, or future execution backend is infrastructure.

The Run is the application-level unit of work.

---

# Making External Actions Safe

When an Agent can change the world, make the boundary explicit.

Prefer:

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

over allowing a model response to directly perform an irreversible side effect.

For actions that may be retried, define idempotency semantics in the tool:

```python
class ChargeCard(Tool):
    idempotent = True  # safe to call again with the same arguments

    def call(self, order_id: str, amount: float) -> str: ...
```

A tool call that raises leaves its effect unknown — there is no way to tell whether the side effect happened before the exception did. `RetryStrategy` only retries a failed call when its tool opts in with `idempotent = True`; otherwise it fails on the first error rather than risking a duplicate charge or a duplicate email.

A retry should not accidentally duplicate a side effect.

---

# Choosing Between Agent Hooks and Strategy

Start with ordinary Agent behavior.

Use lifecycle hooks when you need to customize behavior around the normal execution loop.

Use a custom Strategy only when the loop itself has to work differently.

A useful rule is:

```text
Different behavior?
    → Agent

Different execution mechanics?
    → Strategy
```

This keeps the application model simple.

---

# When to Use a Graph

Do not introduce a graph because the Agent happens to perform multiple steps.

A graph becomes useful when the relationships between steps are themselves the thing you need to model.

For example:

```text
A → B
A → C
B/C → D
```

If ordinary application code expresses the behavior clearly, prefer ordinary application code.

Runa supports orchestration when it is useful.

It does not require orchestration as the default way to think.

---

# Keeping the Agent Definition Readable

Prefer:

```python
class SupportAgent(Agent):
    instructions = """
    Resolve customer issues.
    Create a ticket when necessary.
    """

    tools = [
        KnowledgeBase,
        CreateTicket,
    ]
```

over spreading the definition across several configuration files when there is no real need to do so.

The Agent definition should reveal the application's intent and capabilities.

Beautiful Agent code is part of the framework's design goal.

---

# A Practical Rule

When building something in Runa, ask:

```text
Can I express this with ordinary application code?

Can the Run represent this lifecycle?

Can a Tool represent this capability?

Can existing state concepts represent this data?

Do I actually need a new abstraction?
```

Prefer the smallest model that clearly expresses the application.

> **Add abstractions when the application reveals a recurring problem—not because the framework has a place to put them.**
