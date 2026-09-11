# Runa

## What's Runa?
Runa is an opinionated Python framework for agentic AI.

## Features

- **Tools from function signatures.** `@tool` reads a function's type
  hints and docstring; there's no schema to write by hand.
- **Guardrails as predicates.** `@guardrail` turns a function into a guardrail for inputs/output, agents and tools alike.
- **Subagents in one line.** `.handoff` transfers a conversation to
  another agent; `.delegate` calls it like a tool.
- **Any provider, one string.** `claude-*`, `gpt-*`, `gemini-*`,
  `llama-*`, `deepseek-*`, `qwen-*`, the model name picks the provider.
- **Persistence with zero setup.** `SQLiteSession` remembers a
  conversation across processes; `runa chat` uses it automatically.
- **Memory that writes itself.** retrieves and stores
  durable, user-scoped facts across conversations with no manual calls.
- **MCP servers: exposes an MCP server's tools to the model indistinguishably from `@tool`.**
- **Approval for the calls that matter.** `needs_approval` pauses a tool
  call for a human to sign off, without turning it into a guardrail.
- **Tracing you never asked for.** Every run is a span tree in `runa.db`,
  inspectable with `runa traces` or, visually, `runa ui`.
- **Tests and evals as first-class citizens.** `runa test` for plain
  assertions, `runa eval` for judged, dataset-driven grading.

## Getting Started

1. Install [uv](https://docs.astral.sh/uv/), then Runa:

   ```bash
   uv venv --python 3.14
   source .venv/bin/activate
   uv add git+https://github.com/benybrahim/runa.git
   ```

2. Scaffold a new application:

   ```bash
   runa new myapp
   ```

   where `myapp` is the application name.


3. Change directory to `myapp`, generate an agent, and talk to it:

   ```bash
   cd myapp
   runa generate agent AssistantAgent --model gpt-5.4-nano
   runa chat assistant_agent
   ```

   Run any subcommand with `--help` for options.


4. Fill in the API key for whichever model you use in `.env`, and you're
   running.


5. Follow the guides to keep building your application. You may find the following resources handy:
   * [Getting Started with Runa](https://benybrahim.github.io/runa/getting_started/)
   * [Runa Guides](https://benybrahim.github.io/runa/guides/)
   * [CLI Reference](https://benybrahim.github.io/runa/cli/)

## Read the Zen of Runa

```bash
python -c "from runa import this"
```

## Contributing

We encourage you to contribute to Runa! Check out [CONTRIBUTING.md](CONTRIBUTING.md)

## License

Runa is released under the [MIT License](./LICENSE).
