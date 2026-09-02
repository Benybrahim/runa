# Runa

> The application framework for agentic AI.

Runa is an opinionated Python framework for building agentic applications.

Inspired by the philosophy of Ruby on Rails, Runa provides conventions, batteries-included infrastructure, and a coherent application model for agentic software.

Runa is not another model SDK or agent runtime. It aims to provide the **application layer above them**.

## Why Runa?

Building production agentic applications requires more than an agent loop. Developers need tools, state, persistence, workflows, observability, and evaluation.

Existing SDKs provide many of these pieces individually. Runa aims to bring them together into a coherent application framework.

The goal is simple:

> **Make the common path for building an agentic application extremely simple.**

## Quick Start

```python
from runa import Runa

runa = Runa()


def get_weather(city: str) -> str:
    return f"{city}: sunny"


agent = runa.agent(
    name="weather",
    instructions="Answer weather questions.",
    model="gpt-5.4-nano",
    tools=[get_weather],
)

run = agent.run("What's the weather in Tokyo?")

print(run.output)
````

Runa's conventional application API is `Runa.agent()`. Lower-level primitives such as `Agent` remain available when more control is needed.

## Core Ideas

Runa is built around a small number of core concepts:

```text
Application
    │
    ├── Agents
    ├── Runs
    ├── Tools
    └── Runtime
```

The framework will grow around these primitives as additional application concerns are introduced, including context, state, workflows, and evaluation.

### Replaceable runtimes

Runa keeps the underlying model provider and runtime replaceable.

```text
                 Runa
                   │
          Agentic Application
                   │
        ┌──────────┼──────────┐
        │          │          │
      OpenAI   Anthropic    Other
```

Your application should not need to be tightly coupled to a specific model provider or runtime.

## Project Status

🚧 **Early development**

Runa is experimental and the API will change.

### Current focus

* Agent API
* Run model
* Tool integration
* Runtime abstraction
* End-to-end execution

### Future work

* Durable runs
* Context and state
* Human-in-the-loop
* Workflows
* Evaluation
* Production infrastructure
* Additional runtimes

## Philosophy

Runa is intentionally opinionated.

The project follows principles such as:

* Convention over configuration
* Batteries included
* Small number of powerful primitives
* Simple by default
* Transparent when necessary
* Durability by default
* Evaluation as part of development
* Escape hatches for advanced users
* Replaceable underlying runtimes
* Optimize for the entire agent lifecycle

Read [`RUNA.md`](RUNA.md) for the full design principles.

## Development

Runa uses [uv](https://docs.astral.sh/uv/) for Python environment and dependency management.

```bash
make install
make lint-fix
make check
make test
make clean
```

## Contributing

Runa is open source, but its core is intentionally opinionated.

Before proposing significant changes, please read [`RUNA.md`](RUNA.md) and [`CONTRIBUTING.md`](CONTRIBUTING.md).

## License

[License TBD]
