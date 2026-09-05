<div align="center">
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/brand/mark-dark.svg">
  <img src="assets/brand/mark.svg" width="40" height="40" alt="Runa">
</picture>

# Runa

**The application framework for agentic AI.**

Run agents, not loops.

</div>

---

```python
from runa import Agent, configure, tool


@tool
def get_weather(city: str) -> str:
    return f"{city}: sunny, 22C"


class WeatherAgent(Agent):
    instructions = "Answer weather questions using the get_weather tool."
    tools = [get_weather]


configure(provider="openai")

run = WeatherAgent.run("What's the weather in Tokyo?")

print(run.result)
# "It's sunny and 22C in Tokyo right now."
```

## Why Runa

A model API and a loop get an agent running. A real application needs more: state, persistence, background execution, retries, human approval, observability, evaluation. Most agent code ends up assembling those separately, project by project.

Runa is not another SDK for calling a model. It's the application layer above one — a coherent framework, not an assembled stack.

## The Runa idea

Everything in Runa is organized around one object: the **Run**.

```text
Agent               defines behavior
  ↓
Run                 represents one execution
  ↓
events · state · result · artifacts
  ↓
persistence · background execution · observability · evaluation
```

An Agent is an ordinary class — instructions, tools, hooks. Calling it produces a `Run`, and everything else in the framework — saving it, resuming it, watching it, grading it — is a layer that reads or advances that same `Run`. See [`docs/architecture.md`](docs/architecture.md) for the full breakdown.

## Application structure

```text
myapp/
├── main.py                # entry point — the one place that calls configure()
├── app/
│   ├── agents/             # Agent subclasses
│   ├── tools/               # Tool subclasses
│   ├── resources/            # shared resources (clients, config)
│   ├── evaluations/          # eval cases — runa eval
│   └── tests/                # deterministic tests — runa test
```

`runa new myapp` scaffolds this layout. `runa generate agent Research` adds `app/agents/research_agent.py` the same way; `generate tool` and `generate evaluation` follow suit.

## Developer workflow

```bash
runa new myapp              # scaffold a new application
runa generate agent Research
runa test                   # app/tests/ — deterministic invariants
runa eval                   # app/evaluations/ — probabilistic behavior, graded by a Judge
runa runs show <id>         # replay a Run's timeline
runa runs list --status failed
```

## Philosophy

Runa is intentionally opinionated:

```text
Agents define behavior. Runs define execution.
Convention over configuration.
One lifecycle, many strategies.
State is explicit.
Observability and evaluation are defaults.
Provide sharp knives.
```

The full set of principles lives in [`RUNA.md`](RUNA.md).

## Status

The core API — `Agent`, `Run`, `Executor`/`AsyncExecutor`, persistence, background execution, approval, observability, evaluation, and the CLI — is implemented and tested, and is stable enough to build against. Runa is still young: expect the surface to keep growing (durable/remote persistence backends, richer strategies, additional providers) without changing these foundations.

## Documentation

* [`docs/getting_started.md`](docs/getting_started.md) — a guided first application
* [`docs/concepts.md`](docs/concepts.md) — Runa's core vocabulary
* [`docs/architecture.md`](docs/architecture.md) — the technical architecture and layer boundaries
* [`docs/guides.md`](docs/guides.md) — practical patterns
* [`docs/manifesto.md`](docs/manifesto.md) — why Runa takes this approach
* [`docs/rails-to-runa.md`](docs/rails-to-runa.md) — the Rails inspiration, mapped concept by concept
* [`RUNA.md`](RUNA.md) — the framework's design principles

## Development

Runa uses [uv](https://docs.astral.sh/uv/) and targets Python 3.14.

```bash
make install     # uv sync
make check       # format + lint + test
make hello       # run examples/hello.py
```

## Feedback

Runa is open source but not open to code contributions — it's maintained as
a single coherent point of view rather than a collection of independently
accepted patches. Bug reports and design feedback are genuinely welcome via
[issues](../../issues); see [`CONTRIBUTING.md`](CONTRIBUTING.md) for how,
and [`SECURITY.md`](SECURITY.md) to report a vulnerability privately.

## License

[MIT](LICENSE)
