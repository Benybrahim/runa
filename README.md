# Welcome to Runa

## What's Runa?

Runa is an agent application framework that includes everything needed to
build and run reliable, stateful agents.

## Quick Start

1. Runa hasn't made a tagged release yet. Install it straight from the repo
   with [uv](https://docs.astral.sh/uv/):

    ```bash
    # Set up your virtual environment
    uv venv --python 3.12
    source .venv/bin/activate
   
    # Install dependencies
    uv add git+https://github.com/benybrahim/runa.git
    ```

2. At the command prompt, create a new Runa application:

    ```bash
    runa new myapp
    ```

   where "myapp" is the application name.


3. Write your agent and run it:

    ```python
    class Assistant(Agent):
   
        name = "assistant_agent"
        instructions = instructions
        tools = [now]
        subagents = [Researcher.handoff, Translator.delegate, Summarizer]
        guardrails = [block_empty.input, block_long.output, contains_pii]

   agent = Assistant()
   agent.run_sync("What time is it right now?")
    ```
   Run with `--help` or `-h` for options.


4. Chat with the agent:

    ```bash
    runa chat my_agent
    ```

5. Follow the guides to start developing your application. You may find
   the following resources handy:
    * [Getting Started with Runa](docs/getting_started.md)
    * [Runa Guides](docs/guides.md)


## License

Runa is released under the [MIT License](./LICENSE).
