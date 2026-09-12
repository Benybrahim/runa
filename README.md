# Welcome to Runa

## What's Runa?

Runa is an opiniated Python framework for building agentic AI applications: instead of a wide
menu of configuration options, it gives you a small set of primitives, each
with exactly one sanctioned shape.

Understanding those primitives is key to understanding Runa. They divide
your application into three layers: the **Agent layer**, the **Context
layer**, and the **Infrastructure layer**, with testing, evaluation, and
tracing built in rather than bolted on.

## Agent layer

The _**Agent layer**_ is where your application decides what to do. An
[Agent](https://benybrahim.github.io/runa/agents/) is an LLM equipped with
instructions and tools, always defined as a subclass, never instantiated
directly:

```python
class SupportAgent(Agent):
    name = "support_agent"
    model = "claude-sonnet-5"
    instruction = ""
    tools = [...]
```

[Tools](https://benybrahim.github.io/runa/tools/) let an agent take action in
the world, always a plain function wrapped in `@tool`.
[Guardrails](https://benybrahim.github.io/runa/guardrails/) validate what
goes in and what comes out, tripping in list order so the first failure
stops the rest. [Human Approval](https://benybrahim.github.io/runa/approval/)
pauses a run before a sensitive tool call executes, until a person signs
off. [Subagents](https://benybrahim.github.io/runa/subagents/) let one agent
delegate or hand off work to another.

## Context layer

The _**Context layer**_ is what an agent remembers between and within runs.
[Sessions](https://benybrahim.github.io/runa/sessions/) hold the
conversation for a single run.
[Memory](https://benybrahim.github.io/runa/memory/) carries facts forward
across runs. [Knowledge](https://benybrahim.github.io/runa/knowledge/) gives
an agent access to your domain's documents, retrieved rather than pasted
into the prompt.

## Infrastructure layer

The _**Infrastructure layer**_ is responsible for connecting an agent to the
outside world and to the model that powers it.
[MCP Servers](https://benybrahim.github.io/runa/mcp/) expose external tools
and resources over the Model Context Protocol.
[Models](https://benybrahim.github.io/runa/models/) are configured per
agent, not globally, so different agents can run on different providers.
Hooks let you observe or intercept a run at well-defined points without
subclassing.

## Built in, not bolted on

Every run is traced automatically as a span tree
([Tracing](https://benybrahim.github.io/runa/tracing/)), so you can see
exactly what an agent did and why. Evaluation
([Eval](https://benybrahim.github.io/runa/evaluation/)) grades correctness
with plain assertions or judged, dataset-driven scoring.

## Getting Started

1. Install [uv](https://docs.astral.sh/uv/), then Runa:

   ```bash
   uv venv --python 3.14
   source .venv/bin/activate
   uv add runa-ai
   ```

2. Scaffold a new application:

   ```bash
   runa new myapp
   ```

   where `myapp` is the application name.

3. Change directory to `myapp`, generate an agent, and talk to it:

   ```bash
   cd myapp
   runa generate agent AssistantAgent --model claude-sonnet-5
   runa chat assistant_agent
   ```

   Run any subcommand with `--help` for options.

4. Fill in the API key for whichever model you use in `.env`, and you're
   running.

5. Follow the guides to keep building your application. You may find the
   following resources handy:
   * [Getting Started with Runa](https://benybrahim.github.io/runa/getting_started/)
   * [Runa Guides](https://benybrahim.github.io/runa/guides/)
   * [CLI Reference](https://benybrahim.github.io/runa/cli/)

## Read the Zen of Runa

```bash
python -c "from runa import this"
```

## Contributing

We encourage you to contribute to Runa! Check out
[CONTRIBUTING.md](CONTRIBUTING.md) for guidelines about how to proceed.

Trying to report a possible security vulnerability in Runa? Please check
out [SECURITY.md](SECURITY.md) for guidelines about how to proceed.

Everyone interacting in Runa's codebase, issue tracker, and discussions is
expected to follow the [code of conduct](CODE_OF_CONDUCT.md).

## License

Runa is released under the [MIT License](./LICENSE).
