# Runa

> The application framework for agentic AI.

Runa is an opinionated Python framework for building agentic applications.

Inspired by the philosophy of Ruby on Rails, Runa brings conventions, batteries-included infrastructure, and a strong application model to agentic software.

Runa is not another model SDK or agent runtime.

It aims to provide the application layer above them.

## Why Runa?

Building production agentic applications currently means assembling many separate pieces:

- Agent runtimes
- Models
- Tools
- Context and state
- Persistence
- Workflows
- Human approval
- Observability
- Evaluation

Existing SDKs solve parts of this problem.

Runa's goal is to provide a **coherent application framework** around them.

## Quick Start

```python
from runa import Agent, tool


@tool
def get_weather(city: str) -> str:
    return f"{city}: sunny"


agent = Agent(
    name="weather",
    tools=[get_weather],
)

result = agent.run("What's the weather in Tokyo?")

print(result.output)
````

The goal is simple:

> **Make the common path for building an agentic application extremely simple.**

## Core Ideas

Runa is built around a small number of concepts:

```text
Application
    │
    ├── Agents
    ├── Runs
    ├── Context
    ├── Tools
    ├── State
    └── Evaluation
```

The underlying runtime and model provider should remain replaceable.

```text
                 Runa
                   │
          Agentic Application
                   │
        ┌──────────┼──────────┐
        │          │          │
      OpenAI   Anthropic    Other
```

## Project Status

🚧 **Early development**

Runa is currently experimental and the API will change.

Current focus:

* Agent
* Tool
* Run
* Runtime abstraction
* End-to-end execution

Future work includes:

* Durable runs
* Context and state
* Human-in-the-loop
* Workflows
* Evaluation
* Production infrastructure
* Additional runtimes

## Philosophy

Runa is intentionally opinionated.

Read [`RUNA.md`](RUNA.md) for the project's design principles and [`CONTRIBUTING.md`](CONTRIBUTING.md) for development and contribution guidelines.

## Development

```bash
git clone <repository-url>
cd runa

python -m venv .venv
source .venv/bin/activate

pip install -e ".[dev]"

pytest
```

## Contributing

Runa is open source, but its core is intentionally opinionated.

Before proposing significant changes, please read [`RUNA.md`](RUNA.md) and [`CONTRIBUTING.md`](CONTRIBUTING.md).

## License

[License TBD]


