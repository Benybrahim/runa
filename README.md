# Welcome to Runa

## What's Runa?

Runa is an agent application framework that includes everything needed to
build and run reliable, stateful agents.

## Quick Start

1. Runa hasn't made a tagged release yet. Install it straight from the repo
   with [uv](https://docs.astral.sh/uv/):

    ```bash
    git clone https://github.com/Benybrahim/runa.git
    cd runa
    make install
    ```

2. At the command prompt, create a new Runa application:

    ```bash
    runa new myapp
    ```

   where "myapp" is the application name.


3. Change directory to `myapp`, define an Agent:

    ```bash
    cd myapp
    runa generate agent MyAgent
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
