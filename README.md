# Runa

## What's Runa?

Runa is an opinionated Python framework for agentic AI. Instead of a wide
menu of configuration options, it gives you a small set of primitives,
with clear conventions:

- **Agents:** which are LLMs equipped with instructions and tools
- **Tools:** the actions an agent can take in the outside world, described clearly enough that the agent knows when and how to use them.
- **Guardrails:** checks that keep what goes into and comes out of an agent or tool within bounds.
- **Delegation:** how agents hand off work to each other, either passing a task along completely or asking for help and getting an answer back.
- **Context management:** what an agent remembers: session, memory, and domain knowledge.

Observability and evaluation come built in, not bolted on: every run is
traced automatically as a span tree, and evaluation grade
correctness with plain assertions or judged, dataset-driven scoring.


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
