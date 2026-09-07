# Welcome to Runa

## What's Runa?

Runa is an agent application framework that includes everything needed to
build and run reliable, stateful agents.

## Features

- [Observability](docs/concepts.md#observability), to watch a Run live or replay its event history afterward
- [Evaluation](docs/concepts.md#evaluation), a harness to grade Agent behavior against cases, distinct from deterministic tests
- [A CLI](docs/cli.md), to scaffold and operate an application

## Getting Started

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


4. Run the agent:

    ```bash
    runa run MyAgent "..."
    ```

5. Follow the guides to start developing your application. You may find
   the following resources handy:
    * [Getting Started with Runa](docs/getting_started.md)
    * [Runa Guides](docs/guides.md)

## Contributing

We encourage you to contribute to Runa! Please check out the
[Contributing to Runa guide](./CONTRIBUTING.md) for guidelines about how to proceed.

Trying to report a possible security vulnerability in Runa? Please
check out our [security policy](./SECURITY.md) for guidelines about how to proceed.

Everyone interacting in Runa is expected to follow the Runa [code of conduct](./CODE_OF_CONDUCT.md).

## License

Runa is released under the [MIT License](./LICENSE).
