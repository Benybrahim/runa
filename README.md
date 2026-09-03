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
├── core/            Run, Message, Event, Artifact, State — pure data
├── agent.py         Agent: declarative tools, instructions, approval, hooks
├── tool.py          Tool base + @tool function adapter
├── runtime/         Strategy + Executor (sync and async) — drives a Run to completion
├── providers/       Thin adapters to model APIs (Anthropic, OpenAI; sync and async)
├── persistence/      RunStore — durable Run status
├── background/       run_later() — background execution
├── approval.py       requires_approval — human-in-the-loop gate
├── observability/     timeline() + instrument() — reads Run.events
├── eval/              expect(run) + run_evals() — same code path as prod
└── cli/               `runa new`, `runa generate agent`, `runa eval`, `runa runs show`
```

Every layer is defined in terms of the `Run`: persistence stores it, background execution changes when it advances, observability reads its event log, evaluation replays and scores it. See [`docs/architecture.md`](docs/architecture.md) for the full layer-by-layer breakdown.

### Replaceable runtimes

Runa keeps the underlying model provider replaceable. A `Provider` is a small protocol (`complete(messages, tools, model) -> Message`); `AnthropicProvider` and `OpenAIProvider` are thin, one-directional adapters to that protocol, and nothing outside `providers/` ever branches on which one is active.

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

### One lifecycle, many transitions

Every `Run` moves through the same state machine — `Created → Queued → Running → Paused / AwaitingApproval → Completed / Failed / Cancelled`. Background execution (`run_later`) and human approval (`requires_approval`, `approve`/`deny`) aren't separate systems; they're alternate transitions through that same machine, so persistence, observability, and evaluation all work identically regardless of how a Run got where it is.

### Application layout

`runa new myapp` scaffolds a conventional project layout — structure, not configuration, carries the meaning (manifesto §2), the same way Rails' `app/models`/`app/controllers` do:

```text
myapp/
├── main.py                  # entry point — the one place that calls configure()
├── app/
│   ├── agents/               # Agent subclasses
│   ├── tools/                 # Tool subclasses
│   ├── resources/              # shared resources (clients, config)
│   └── evaluations/            # eval cases
├── pyproject.toml
└── README.md
```

`runa generate agent Research` adds `app/agents/research_agent.py` with the `Agent` subclass skeleton. `main.py` is a plain script the developer runs (`python main.py`), not an import-time side effect of the `app` package — a `Provider` can do real work in `__init__` (e.g. `OpenAIProvider` builds a client that fails fast without credentials), so auto-configuring on `import app` would break importing an agent or tool module for anyone without a key set. Explicit beats implicit here (manifesto §7).

`runa eval` imports `main.py` (so `configure()` runs) and every module under `app/evaluations/` — each must define module-level `agent` and `cases` — and runs them through `run_evals()`, printing a PASS/FAIL line per case (manifesto §12). `runa runs show <id>` looks the id up in the app's configured `RunStore` and prints `timeline(run)` (manifesto §11); it only finds runs across process boundaries once the app passes a durable store to `configure(provider=..., run_store=SQLiteRunStore(...))` — the default is in-memory.

## Project Status

✅ **MVP complete**

All layers described in [`docs/architecture.md`](docs/architecture.md) are implemented and tested, in build order:

* `core/` — `Run`, `Message`, `Event`, `Artifact`, `State`, `Conversation`
* `Agent` + `Tool` — the declarative surface, including `Agent.as_tool()` for delegation
* `runtime/` — `Strategy` protocol, `DefaultStrategy`, `RetryStrategy`, `Executor`, `AsyncExecutor`
* `providers/` — `AnthropicProvider`, `OpenAIProvider`, `AsyncAnthropicProvider`, `AsyncOpenAIProvider`
* `persistence/` — `RunStore`, `InMemoryRunStore`, `SQLiteRunStore`, `ConversationStore`, `InMemoryConversationStore`
* `background/` + `approval.py` — `run_later`, `Queue` (`InlineQueue`, `ThreadQueue`), `approve`/`deny`
* `observability/` — `timeline()`, `instrument()`
* `eval/` — `expect(run)`, `run_evals()`
* `cli/` — `runa new`, `runa generate agent`, `runa eval`, `runa runs show`

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
