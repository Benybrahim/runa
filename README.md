# Welcome to Runa

---

## What's Runa?

Runa is an agent application framework that includes everything needed to build and run reliable, stateful agents according to the Agent-Run-Execution (ARE) pattern.

Understanding the ARE pattern is key to understanding Runa. ARE divides your agent application into three parts: Agent, Run, and Execution, each with a specific responsibility.

### Agent layer

The Agent layer defines behavior: instructions, tools, hooks, and policies. In Runa, an Agent is an ordinary Python class, not a running process; defining `ResearchAgent` doesn't execute anything by itself, the same way defining a Rails model doesn't touch the database until you call it. See [`docs/concepts.md`](docs/concepts.md) for the full definition.

### Run layer

The Run layer represents execution. Calling an Agent produces a `Run`, with its own identity, lifecycle, events, state, result, and artifacts. Everything else in Runa (saving a Run, resuming it, watching it, grading it) is a layer that reads or advances that same `Run`. See [`docs/architecture.md`](docs/architecture.md) for the full breakdown.

## Frameworks and libraries

The `Executor`/`AsyncExecutor` that drives a Run, and the `Provider` adapters that call a model, can each be used independently of the rest of Runa.

In addition to that, Runa also comes with:

* Persistence, to save and resume a Run or a Conversation across process restarts
* Background execution, to run a Run off the request path and check on it later
* Approval, to route a tool call to a human before it executes
* Observability, to watch a Run live or replay its event history afterward
* Evaluation, a harness to grade Agent behavior against cases, distinct from deterministic tests
* A CLI (`runa new`, `runa generate`, `runa test`, `runa eval`, `runa runs`), to scaffold and operate an application

## Getting Started

Runa hasn't made a tagged release yet. Install from source at the command prompt with [uv](https://docs.astral.sh/uv/):

```bash
$ git clone https://github.com/Benybrahim/runa
$ cd runa
$ make install
```

At the command prompt, create a new Runa application:

```bash
$ uv run runa new myapp
```

where "myapp" is the application name.

Change directory to myapp, define an Agent, and run it:

```bash
$ cd myapp
```

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

Follow the guides to start developing your application. You may find the following resources handy:

* [Getting Started with Runa](docs/getting_started.md)
* [Runa Concepts](docs/concepts.md)
* [The Runa Architecture](docs/architecture.md)
* [Runa Guides](docs/guides.md)
* [The Runa Manifesto](docs/manifesto.md)

## Feedback

Runa is open source, but it's not open to code contributions: it's maintained as a single coherent point of view rather than a collection of independently accepted patches. Pull requests are closed unmerged; check out [`CONTRIBUTING.md`](CONTRIBUTING.md) for the full policy.

Bug reports and design feedback are genuinely welcome. Please open an [issue](../../issues).

Trying to report a possible security vulnerability in Runa? Please check out [`SECURITY.md`](SECURITY.md) for guidelines about how to proceed.

Everyone interacting in Runa's codebase, issue tracker, and any chat rooms is expected to follow the [Runa code of conduct](CODE_OF_CONDUCT.md).

## License

Runa is released under the [MIT License](LICENSE).
