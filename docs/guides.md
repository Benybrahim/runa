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

# Giving the Agent Context

Populate `run.context` before running the Agent when it needs information the application already has:

```python
run = Run(input="What's the refund policy on order A123?")
run.context.resources = [kb_article]
run.context.policies = ["no refunds over $500 without approval"]

ResearchAgent.run(run.input, executor=Executor(provider=..., ...))
```

A non-empty Context reaches the Agent as a second system message, right after `Agent.instructions` — a plain listing of whatever keys are set. No key name is treated specially; Context stays free-form, the same way Run State and Conversation State do.

An empty Context (the default) adds nothing — most simple agents never need one.

If a different shape belongs in the prompt than the default listing gives, don't populate `run.context`; build the message directly in `before_run`/`plan` instead.

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

Only sequence Runs against a shared Conversation this way — finish one (including
the `record()` that happens at the end of `.run()`) before starting the next.
Two Runs launched concurrently against the same Conversation (e.g. via
`run_later()` on a `ThreadQueue`) are not merged: each seeds its history from
the Conversation as it stood when that Run started, and whichever finishes
last silently overwrites the other's turn. Give concurrent Runs their own
Conversations and merge deliberately instead.

A Conversation's history has no built-in limit — every Run's turn is added
on top of the last, forever. Eventually that history is large enough that
the model API itself rejects it (a Provider error, which fails the Run
cleanly rather than crashing — but the Conversation stays stuck failing
every Run after that until something trims it). Runa doesn't truncate or
summarize this automatically — that would mean building the kind of
agent-specific memory system the framework deliberately avoids.
`conversation.messages` is a plain list, so manage it the way any
application-owned list would be managed:

```python
conversation.messages = conversation.messages[-40:]  # keep the last N turns
```

or fold older turns into `conversation.state` as a summary first, if losing
raw history isn't acceptable.

---

# Running in the Background

Use `run_later()` when work should not execute as part of the immediate call:

```python
run = ResearchAgent.run_later("Produce a detailed report.")
```

The returned object represents the same conceptual unit of work as `run()`.

For durable background execution, configure a persistent Run store and an appropriate Queue — `configure(provider=..., run_store=SQLiteRunStore(...))`. `run_later()` saves the Run there itself when queuing onto a `DurableQueue` — once before dispatch (so recovery has something to find after a crash) and again once the Run reaches its next pause point (completion, failure, or an approval gate), so `runa runs show <id>` reflects what actually happened instead of the Run's last-queued status. No extra wiring needed beyond `configure()`.

Do not create a separate “job object” in application code just because execution happens later.

If the queue is a `DurableQueue` (e.g. `SQLiteQueue`), it journals which Run
is mid-flight, so work survives a process crash. Recover orphaned Runs once
at startup:

```python
from runa import recover_pending

recover_pending(queue, run_store, executor, agents=[ResearchAgent])
```

This restarts a recovered Run from the beginning, not from wherever the crashed process reached — nothing checkpoints progress once a Run starts executing, only before dispatch and at its next pause point. Any tool call the crashed process already completed runs again. Only pass `agents` whose tools are all `idempotent = True`, or a real side effect (a charge, an email, a ticket) can happen twice.

## Shutting Down a Background Queue

`ThreadQueue`/`SQLiteQueue` run jobs on a `ThreadPoolExecutor`. A normal
process exit — the script falls off the end, or `sys.exit()` — already
waits for in-flight jobs to finish before the interpreter actually
terminates; that's Python's own `ThreadPoolExecutor` behavior, not
something Runa adds, and it works even if the application never calls
`queue.close()`.

`SIGTERM` — how Docker, Kubernetes, and systemd all ask a process to stop —
does not go through that same path. With no handler installed, the default
action for SIGTERM is immediate termination: whatever a worker thread was
doing (mid-tool-call, mid-model-call) simply stops, with no chance to run
cleanup code. If the application needs in-flight background Runs to finish
before a SIGTERM-driven shutdown completes, it has to say so itself:

```python
import signal


def handle_sigterm(signum, frame):
    queue.close(wait=True)  # block until running jobs finish
    raise SystemExit(0)


signal.signal(signal.SIGTERM, handle_sigterm)
```

Registering a signal handler is an application decision, not something
Runa does on the application's behalf — a web server or job runner already
managing its own SIGTERM handling shouldn't have Runa silently install a
competing one.

For work where losing in-flight progress to `SIGKILL` (which no signal
handler can intercept at all) is unacceptable, durability is the real
answer, not a longer grace period: use a `DurableQueue` (`SQLiteQueue`) and
call `recover_pending()` at the next startup, as above. A `SIGTERM` handler
and `DurableQueue` recovery address different failure windows — the handler
covers an orderly stop with time to finish; recovery covers whatever the
handler didn't reach in time, or a harder kill that skipped it entirely.

---

# Inspecting Runs

A Run records execution events.

In-process, the timeline is always available, on any Run, with no setup:

```python
from runa.observability import timeline

run = ResearchAgent.run("...")
for entry in timeline(run):
    print(entry.timestamp, entry.summary)
```

The CLI reads the same information back from a `RunStore` instead, so it
only sees Runs that were actually saved there — `run_later()` saves
automatically, but only when given a `DurableQueue` (see "Running in the
Background" above; that's what lets `runa runs show` follow background
work after a crash). A plain synchronous `Agent.run()`, and `run_later()`
on the default `InlineQueue`, save nothing, on purpose (persistence stays
outside the core execution primitive). Save one explicitly if you want to
inspect it later from the CLI instead of in-process:

```python
from runa.config import default_run_store

run = ResearchAgent.run("...")
default_run_store().save(run)
```

```bash
runa runs show <id>
runa runs list --status failed --agent-name ResearchAgent
runa runs pending
```

`runs list` filters by `--status`, `--since`, `--agent-name`, and
`--parent-run-id`. `runs pending` lists Runs paused in
`AWAITING_APPROVAL` — see "Adding Human Approval" below for
`runs approve`/`runs deny`.

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

From the CLI:

```bash
runa test    # runs app/tests/
runa eval    # runs app/evaluations/
```

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

From the CLI:

```bash
runa runs approve <run_id> <tool_call_id>
runa runs deny <run_id> <tool_call_id> --reason "not authorized"
```

Or from application code, via `runa.approve()`/`runa.deny()` — see
`approval.py`.

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

# Cancelling a Run

A Run being driven in-process — for example by a `ThreadQueue` job — should
be cancelled by requesting it, not by mutating the Run directly:

```python
run.request_cancel()
```

The owning `Executor`/`AsyncExecutor` checks this once per step and performs
the actual cancellation itself, at the next step boundary. Calling
`run.cancel()` directly from a different thread than the one driving the Run
races that loop and can raise `IllegalTransition`.

A Run with no live Executor driving it — one saved to a `RunStore` while
`CREATED`, `QUEUED`, `PAUSED`, or `AWAITING_APPROVAL` — has no owning thread
to race, so it can be cancelled directly:

```bash
runa runs cancel <run_id>
```

---

# Bounding a Run's Wall-Clock Time

`max_steps` bounds how many steps a Run can take; `timeout` bounds how long a single `run()` call may take:

```python
executor = Executor(provider, timeout=30)  # seconds
```

Like `max_steps`, this is checked at the step boundary, not preemptively — a slow model or tool call already in flight still finishes before the next check can fail the Run. A Run that exceeds either bound fails with a clear error rather than hanging or looping forever.

The budget is per `run()` call, not per Run: resuming a paused Run (background handoff, approval) starts a fresh timeout rather than counting time spent waiting.

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

Declare Policy checks on the Agent for rules the application can decide on
its own, without a human:

```python
def block_large_transfers(run, tool_call) -> bool:
    return tool_call.arguments.get("amount", 0) <= 10_000


class FinanceAgent(Agent):
    tools = [TransferFunds]
    policies = [block_large_transfers]
    requires_approval = [TransferFunds]  # still gate the rest on a human
```

A Policy that returns `False` fails the Run outright, before it can ever
reach approval. Use Policy for rules that are always true regardless of who
is watching; use `requires_approval` for the calls that should always get
a human decision.

For actions that may be retried, define idempotency semantics in the tool:

```python
class ChargeCard(Tool):
    idempotent = True  # safe to call again with the same arguments

    def call(self, order_id: str, amount: float) -> str: ...
```

A tool call that raises leaves its effect unknown — there is no way to tell whether the side effect happened before the exception did. `RetryStrategy` only retries a failed call when its tool opts in with `idempotent = True`; otherwise it fails on the first error rather than risking a duplicate charge or a duplicate email.

A retry should not accidentally duplicate a side effect.

---

# Retrying Transient Model Errors

`RetryStrategy` covers tool calls, not the model call itself. A rate limit,
timeout, or dropped connection from the model API fails the whole Run
immediately unless the Provider is wrapped in `RetryingProvider` (or
`AsyncRetryingProvider` for `run_async()`):

```python
from runa import configure, RetryingProvider
from runa.providers import AnthropicProvider

configure(provider=RetryingProvider(AnthropicProvider(), max_retries=3))
```

This is safe by construction, not just by convention: `Executor._call_model`
only writes the response to `Run.messages` once `complete()` returns, so a
failed attempt hasn't changed anything a retry could duplicate — unlike a
tool call, no `idempotent` flag is needed here.

By default every exception is retried, with exponential backoff starting at
`backoff` seconds. To retry only specific failures — e.g. a provider's own
rate-limit or connection-error types — pass `is_retryable`:

```python
import anthropic

configure(
    provider=RetryingProvider(
        AnthropicProvider(),
        is_retryable=lambda exc: isinstance(
            exc, anthropic.RateLimitError | anthropic.APIConnectionError
        ),
    )
)
```

Only `complete()` is retried — a `RetryingProvider` wrapping a streaming
Provider no longer satisfies `StreamingProvider`, since a partially
delivered stream can't be safely restarted once some chunks have already
reached `on_chunk`.

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
