# Runa

> The application framework for agentic AI.

Runa is an opinionated Python framework for building agentic applications.

Inspired by the philosophy of Ruby on Rails, Runa provides conventions, batteries-included infrastructure, and a coherent application model for agentic software.

Runa is not another model SDK or agent runtime. It aims to provide the **application layer above them**.

## Why Runa?

Building production agentic applications requires more than an agent loop. Developers need tools, state, persistence, background execution, human approval, observability, and evaluation.

Existing SDKs provide many of these pieces individually. Runa brings them together into a coherent application framework.

The goal is simple:

> **Make the common path for building an agentic application extremely simple.**

## Quick Start

```python
from runa import Agent, OpenAIProvider, configure, tool

configure(provider=OpenAIProvider())


@tool
def get_weather(city: str) -> str:
    return f"{city}: sunny"


class WeatherAgent(Agent):
    instructions = "Answer weather questions."
    tools = [get_weather]


run = WeatherAgent.run("What's the weather in Tokyo?")

print(run.status)
# completed

print(run.result)
# "It's sunny in Tokyo right now."
```

(`run.result` comes from a live model call, so the exact wording varies — the status and shape of the result don't.)

## Core Ideas

Runa is built around one central object — the `Run` — and a small set of layers around it:

```text
runa/
├── core/            Run, Message, Event, Artifact, State, Context — pure data
├── agent.py         Agent: declarative tools, instructions, policies, approval, hooks
├── tool.py          Tool base + @tool function adapter
├── runtime/         Strategy + Executor (sync and async) — drives a Run to completion
├── providers/       Thin adapters to model APIs (Anthropic, OpenAI; sync and async)
├── persistence/      RunStore — durable Run status
├── background/       run_later(), DurableQueue/recover_pending() — background execution + crash recovery
├── approval.py       requires_approval — human-in-the-loop gate
├── observability/     timeline() + instrument() — reads Run.events
├── eval/              expect(run) + run_evals() + Judge — same code path as prod
└── cli/               `runa new`, `runa generate agent`, `runa eval`, `runa test`, `runa runs show`/`list`
```

Every layer is defined in terms of the `Run`: persistence stores it, background execution changes when it advances, observability reads its event log, evaluation replays and scores it. See [`docs/architecture.md`](docs/architecture.md) for the full layer-by-layer breakdown.

### Replaceable runtimes

Runa keeps the underlying model provider replaceable. A `Provider` is a small protocol (`complete(messages, tools, model) -> Message`); `AnthropicProvider` and `OpenAIProvider` are thin, one-directional adapters to that protocol, and nothing outside `providers/` ever branches on which one is active.

### Streaming is an opt-in callback, not a second execution path

`complete()` always returns one whole `Message` — fine for most agent code, but a chat-shaped consumer often wants to show text as it's generated. `Executor.run(agent, run, on_chunk=...)` is that opt-in: pass a callback and it receives a `StreamChunk` for every text delta as each model call streams in, while the Run's messages, events, and final state end up identical to the non-streaming path — `on_chunk` only changes what's observed while a `CallModel` step is in flight, so it composes with tools, retries, and approval automatically, with no separate streaming-aware Strategy or Run type.

```python
def on_chunk(chunk: StreamChunk) -> None:
    print(chunk.delta, end="", flush=True)


run = Executor(OpenAIProvider()).run(
    WeatherAgent(), Run(input="..."), on_chunk=on_chunk
)
```

This requires a `StreamingProvider` — `AnthropicProvider` and `OpenAIProvider` both implement `stream()` alongside `complete()`, returning a `Stream` (or, on the async side, an `AsyncStream`) that's lazy: the request only fires once it's actually iterated. Passing `on_chunk` to a Provider that doesn't implement `stream()` fails the Run with a clear error, the same way any other bad configuration does, rather than silently falling back to `complete()`. See `examples/streaming.py` for a complete runnable version.

### Async is a parallel path, not a rewrite

`Agent.run_async()` drives an `AsyncExecutor` against an `AsyncProvider` (`AsyncAnthropicProvider`, `AsyncOpenAIProvider`) — same `Run`/`Strategy` contract as the sync path, so persistence, observability, and eval all work identically either way. It buys two things the sync path can't: I/O-bound tools/providers that don't tie up a thread, and independent tool calls from one model turn running concurrently via `asyncio.gather` instead of one at a time. A `Tool.call` may be `async def` or a plain function — `AsyncExecutor` awaits one and runs the other through `asyncio.to_thread`; the sync `Executor` raises a clear error if handed an async-only tool rather than mishandling it silently.

```python
configure(provider=AnthropicProvider(), async_provider=AsyncAnthropicProvider())

run = await ResearchAgent.run_async(
    "What are the most promising approaches to fusion energy?"
)
```

```text
                 Runa
                   │
          Agentic Application
                   │
        ┌──────────┼──────────┐
        │          │          │
      OpenAI   Anthropic    Other
```

### Delegation is just a tool

Some agents delegate to other agents. Runa doesn't add a second orchestration layer for that — `Agent.as_tool()` wraps an agent as an ordinary `Tool`, so a parent agent declares it exactly like any other capability:

```python
class ResearchAgent(Agent):
    instructions = "Answer research questions concisely."


class LeadAgent(Agent):
    instructions = "Delegate research questions to the ResearchAgent tool."
    tools = [ResearchAgent.as_tool()]
```

The sub-agent runs to completion and its `run.result` comes back as the tool's output; a sub-run that fails surfaces as an ordinary failed tool call. `DefaultStrategy`'s existing tool-use loop handles it — delegation didn't need a new `Strategy`.

For a parent driven by `AsyncExecutor`/`run_async()`, `Agent.as_async_tool()` is the async counterpart: its `call()` is `async def` and delegates through `AsyncExecutor` instead of a thread, so when a model turn requests several sub-agents at once, `AsyncExecutor`'s existing concurrent tool-call batching (see "Async is a parallel path" above) runs them as genuine concurrent async I/O rather than one thread per delegate:

```python
class LeadAgent(Agent):
    instructions = "Delegate research and news questions to their agents."
    tools = [ResearchAgent.as_async_tool(), NewsAgent.as_async_tool()]
```

See `examples/parallel_delegate.py` for a runnable version where the model calls both sub-agents in one turn.

### A Tool result can be an Artifact

Agents produce more than text (manifesto §10) — reports, extracted data, files, plans. A `Tool.call()` that returns an `Artifact` (`TextArtifact`, `DataArtifact`, `FileArtifact`, `CitationSetArtifact`, `PlanArtifact`, `ActionArtifact`) has it recorded on `run.artifacts` automatically; a plain return value behaves exactly as before. No separate API to remember — the Executor dispatches on the result's type (manifesto §2: "types are configuration"):

```python
class ExtractInvoiceData(Tool):
    def call(self, text: str) -> DataArtifact:
        return DataArtifact(data={"total": 129.99, "vendor": "Acme Corp"})
```

The model still sees a plain-text tool result — `Artifact.summary()` renders it (each subclass overrides it sensibly; override it yourself on a custom Artifact for custom wording).

### Context reaches the Agent automatically

State is what the application owns; Context is what the Agent is given (manifesto §7). Populate `run.context` before running, and it's seeded as a second system message — right after `Agent.instructions` — before the model ever sees the input:

```python
run = Run(input="What's the refund policy on order A123?")
run.context.resources = [kb_article]
run.context.policies = ["no refunds over $500 without approval"]
```

Context is deliberately free-form — every key reaches the Agent the same generic way, with nothing in the framework interpreting specific key names. An empty Context (the default) adds nothing, so the common case is unchanged; an application whose Context needs a different shape in the prompt keeps the escape hatch of building the message directly in `before_run`/`plan` instead.

### Planning and reflection are hooks, not a new subsystem

Manifesto §6 lists `before_run`, `plan`, `review`, and `after_run` as opt-in `Agent` hooks without prescribing what they do — "the framework standardizes execution without standardizing thought." `plan()` runs once before the tool-use loop starts and can freely mutate `run.state`/`run.messages`, so whatever it adds is visible to every step that follows. `review()` runs once when the Strategy is about to complete the Run, and its return value — if not `None` — replaces the Strategy's draft result, which is what makes it useful for reflection rather than just observation:

```python
class ResearchAgent(Agent):
    def plan(self, run: Run) -> None:
        run.state.plan = provider.complete(...).content

    def review(self, run: Run) -> str | None:
        draft = run.messages[-1].content
        return provider.complete(...).content or draft  # None keeps the draft
```

See `examples/plan_and_review.py` for a complete version that calls the model from both hooks.

### One lifecycle, many transitions

Every `Run` moves through the same state machine — `Created → Queued → Running → Paused / AwaitingApproval → Completed / Failed / Cancelled`. Background execution (`run_later`) and human approval (`requires_approval`, `approve`/`deny`) aren't separate systems; they're alternate transitions through that same machine, so persistence, observability, and evaluation all work identically regardless of how a Run got where it is.

Cancellation follows the same rule but needs one more step: only the thread actually driving a Run may call `run.cancel()` safely, since it's also mutating `.status`/`.events`. `run.request_cancel()` sets a plain flag any thread can set anytime; `Executor`/`AsyncExecutor` check it once per step and cancel the Run themselves, at the next step boundary. A Run with no live Executor (paused, awaiting approval, or still queued in a `RunStore`) has no thread to race, so `run.cancel()` — or `runa runs cancel <id>` — works directly there.

`Executor(provider, timeout=30)`/`AsyncExecutor(provider, timeout=30)` bound a `run()` call's wall-clock time the same way `max_steps` bounds its step count — checked at that same step boundary, not preemptively, so a slow call already in flight still finishes before the next check can fail the Run. The budget is per `run()` call: resuming a paused Run starts fresh rather than counting time spent waiting.

### Policy runs before approval

`requires_approval` always defers to a human. `Agent.policies` is the earlier, programmatic check for rules the application can decide on its own — a plain `(run, tool_call) -> bool` — so a call can be denied outright without ever pausing a Run for a person:

```python
def block_large_transfers(run: Run, tool_call: ToolCall) -> bool:
    return tool_call.arguments.get("amount", 0) <= 10_000


class FinanceAgent(Agent):
    tools = [TransferFunds]
    policies = [block_large_transfers]  # denies on its own
    requires_approval = [TransferFunds]  # everything else still needs a human
```

A denying policy fails the Run and emits a `POLICY_DENIED` event — the tool itself never runs.

### Application layout

`runa new myapp` scaffolds a conventional project layout — structure, not configuration, carries the meaning (manifesto §2), the same way Rails' `app/models`/`app/controllers` do:

```text
myapp/
├── main.py                  # entry point — the one place that calls configure()
├── app/
│   ├── agents/               # Agent subclasses
│   ├── tools/                 # Tool subclasses
│   ├── resources/              # shared resources (clients, config)
│   ├── evaluations/            # eval cases — runa eval
│   └── tests/                  # deterministic tests — runa test
├── pyproject.toml
└── README.md
```

`runa generate agent Research` adds `app/agents/research_agent.py` with the `Agent` subclass skeleton. `main.py` is a plain script the developer runs (`python main.py`), not an import-time side effect of the `app` package — a `Provider` can do real work in `__init__` (e.g. `OpenAIProvider` builds a client that fails fast without credentials), so auto-configuring on `import app` would break importing an agent or tool module for anyone without a key set. Explicit beats implicit here (manifesto §7).

`runa eval` imports `main.py` (so `configure()` runs) and every module under `app/evaluations/` — each must define module-level `agent` and `cases` — and runs them through `run_evals()`, printing a PASS/FAIL line per case (manifesto §12). Cases may assert structure (`to_be_completed()`, `to_have_called(...)`, `to_have_error(...)`) or behavior via a `Judge` (`to_be_helpful()`, `to_be_factual()`, `not_to_hallucinate()`, or a custom `to_satisfy(rubric)`) — the latter make a real, non-deterministic model call to grade the Run's transcript.

`runa test` imports `main.py` and every module under `app/tests/`, running each `test_*` function and reporting PASS/FAIL the same way — the deterministic half of manifesto §12: plain `assert` statements against a Run (`assert run.result == "..."`), not a graded rubric. It's a small runner of its own rather than a pytest wrapper, so a generated app carries no test-framework dependency beyond `runa` itself.

`runa runs show <id>` looks the id up in the app's configured `RunStore` and prints `timeline(run)` (manifesto §11); it only finds runs across process boundaries once the app passes a durable store to `configure(provider=..., run_store=SQLiteRunStore(...))` — the default is in-memory. `runa runs list [--status STATUS] [--since TIMESTAMP]` answers the question one Run's timeline can't — "what happened across every Run" — by filtering `RunStore.list()` itself: `InMemoryRunStore` filters in Python, `SQLiteRunStore` pushes both filters into the `WHERE` clause using the `status`/`created_at` columns it already keeps outside the JSON blob, so listing doesn't deserialize every row just to discard most of them.

## Project Status

✅ **MVP complete**

All layers described in [`docs/architecture.md`](docs/architecture.md) are implemented and tested, in build order:

* `core/` — `Run`, `Message`, `Event`, `Artifact` (auto-recorded when a Tool returns one), `State`, `Context`, `Conversation`
* `Agent` + `Tool` — the declarative surface: `tools`, `policies`, `requires_approval`, hooks, and `Agent.as_tool()`/`as_async_tool()` for delegation
* `runtime/` — `Strategy` protocol, `DefaultStrategy`, `RetryStrategy`, `Executor`, `AsyncExecutor`, `on_chunk` streaming via `StreamingProvider`/`AsyncStreamingProvider`
* `providers/` — `AnthropicProvider`, `OpenAIProvider`, `AsyncAnthropicProvider`, `AsyncOpenAIProvider`, each also implementing `stream()`
* `persistence/` — `RunStore`, `InMemoryRunStore`, `SQLiteRunStore`, `ConversationStore`, `InMemoryConversationStore`
* `background/` + `approval.py` — `run_later`, `Queue` (`InlineQueue`, `ThreadQueue`, `SQLiteQueue`), `DurableQueue`/`recover_pending()` for crash recovery, `approve`/`deny`, `Run.request_cancel()` for cooperative cancellation
* `observability/` — `timeline()`, `instrument()`
* `eval/` — `expect(run)`, `run_evals()`, `Judge` (LLM-graded `to_be_helpful()`/`to_be_factual()`/`not_to_hallucinate()`/`to_meet_the_goal()`)
* `cli/` — `runa new`, `runa generate agent`, `runa eval`, `runa test`, `runa runs show`/`list`/`pending`/`approve`/`deny`/`cancel`

The core API is stable enough to build against, but Runa is still young — expect the surface to keep growing (durable/remote persistence backends, richer strategies, additional providers) without changing these foundations.

## Philosophy

Runa is intentionally opinionated. Its principles, in full, live in [`RUNA.md`](RUNA.md):

1. Optimize for developer happiness
2. Convention over configuration
3. Omakase agent infrastructure
4. Agents are objects, not graphs
5. The Run is the primary unit of computation
6. One lifecycle, many strategies
7. State is explicit
8. Observability and evaluation are defaults
9. Provide sharp knives

## Development

Runa uses [uv](https://docs.astral.sh/uv/) for Python environment and dependency management, and targets Python 3.14.

```bash
make install     # uv sync
make format      # ruff format
make lint        # ruff check
make lint-fix    # ruff check --fix
make typecheck   # pyright
make test        # pytest
make check       # format + lint + test
make hello       # run examples/hello.py
make examples    # run every example in examples/
make clean
```

## Contributing

Runa is open source, but its core is intentionally opinionated.

Before proposing significant changes, please read [`RUNA.md`](RUNA.md) and [`CONTRIBUTING.md`](CONTRIBUTING.md).

## License

[License TBD]
