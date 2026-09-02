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
# RunStatus.COMPLETED

print(run.result)
# "It's sunny in Tokyo right now."
```

## Core Ideas

Runa is built around one central object — the `Run` — and a small set of layers around it:

```text
runa/
├── core/            Run, Message, Event, Artifact, State — pure data
├── agent.py         Agent: declarative tools, instructions, approval, hooks
├── tool.py          Tool base + @tool function adapter
├── runtime/         Strategy + Executor — drives a Run to completion
├── providers/       Thin adapters to model APIs (Anthropic, OpenAI)
├── persistence/      RunStore — durable Run status
├── background/       run_later() — background execution
├── approval.py       requires_approval — human-in-the-loop gate
├── observability/     timeline() + instrument() — reads Run.events
├── eval/              expect(run) + run_evals() — same code path as prod
└── cli/               `runa new`, `runa generate agent`
```

Every layer is defined in terms of the `Run`: persistence stores it, background execution changes when it advances, observability reads its event log, evaluation replays and scores it. See [`docs/architecture.md`](docs/architecture.md) for the full layer-by-layer breakdown.

### Replaceable runtimes

Runa keeps the underlying model provider replaceable. A `Provider` is a small protocol (`complete(messages, tools, model) -> Message`); `AnthropicProvider` and `OpenAIProvider` are thin, one-directional adapters to that protocol, and nothing outside `providers/` ever branches on which one is active.

```text
                 Runa
                   │
          Agentic Application
                   │
        ┌──────────┼──────────┐
        │          │          │
      OpenAI   Anthropic    Other
```

### One lifecycle, many transitions

Every `Run` moves through the same state machine — `Created → Queued → Running → Paused / AwaitingApproval → Completed / Failed / Cancelled`. Background execution (`run_later`) and human approval (`requires_approval`, `approve`/`deny`) aren't separate systems; they're alternate transitions through that same machine, so persistence, observability, and evaluation all work identically regardless of how a Run got where it is.

## Project Status

✅ **MVP complete**

All layers described in [`docs/architecture.md`](docs/architecture.md) are implemented and tested, in build order:

* `core/` — `Run`, `Message`, `Event`, `Artifact`, `State`
* `Agent` + `Tool` — the declarative surface
* `runtime/` — `Strategy` protocol, `DefaultStrategy`, `Executor`
* `providers/` — `AnthropicProvider`, `OpenAIProvider`
* `persistence/` — `RunStore`, `InMemoryRunStore`
* `background/` + `approval.py` — `run_later`, `approve`/`deny`
* `observability/` — `timeline()`, `instrument()`
* `eval/` — `expect(run)`, `run_evals()`
* `cli/` — `runa new`, `runa generate agent`

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
