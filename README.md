# Welcome to Runa

---

## What's Runa?

Runa is an agent application framework that includes everything needed to
build and run reliable, stateful agents according to the
[Agent-Run-Execution (ARE)](docs/concepts.md#the-agent-run-execution-are-pattern) pattern.

Understanding the ARE pattern is key to understanding Runa. ARE divides your
agent application into three layers: Agent, Execution, and Run, each with a
specific responsibility.

In Runa, _**The Run**_ is the central unit of work.

## Agent layer

The _**Agent layer**_ declares the behavior and capabilities of an agent, such
as its instructions, tools, hooks, policies, and delegation, and encapsulates
the business logic specific to your application. In Runa, Agents are
ordinary Python classes derived from [`Agent`](docs/concepts.md#agent) that define how a kind of agent should behave when invoked. An Agent is a reusable declaration, not a unit of work.

## Execution layer

The _**Execution layer**_ is responsible for progressing an agent's work. It
calls models, invokes tools, applies policies, and determines what happens
next according to the Agent's declared behavior. In Runa, Execution is
handled by the [`Executor`](docs/concepts.md#execution)
driving a [`Strategy`](docs/concepts.md#strategy).

## Run layer

The _**Run layer**_ represents one instance of an Agent doing work. A Run
holds the state and history of that work, such as its input, context,
messages, events, status, artifacts, and result. A [`Run`](docs/concepts.md#run) is the durable unit
of work that infrastructure can persist, observe, resume, and evaluate.

## Features

In addition to that, Runa also comes with:

- [Persistence](docs/concepts.md#persistence), to save and resume a Run or a Conversation across process restarts
- [Background execution](docs/concepts.md#background-execution), to run a Run off the request path and check on it later
- [Approval](docs/concepts.md#approval), to route a tool call to a human before it executes
- [Observability](docs/concepts.md#observability), to watch a Run live or replay its event history afterward
- [Evaluation](docs/concepts.md#evaluation), a harness to grade Agent behavior against cases, distinct from deterministic tests
- [A CLI](docs/cli.md), to scaffold and operate an application

## Getting Started

1. Runa hasn't made a tagged release yet. Install from source at the command
   prompt with [uv](https://docs.astral.sh/uv/):

    ```bash
    $ git clone https://github.com/Benybrahim/runa
    $ cd runa
    $ make install
    ```

2. At the command prompt, create a new Runa application:

    ```bash
    $ runa new myapp
    ```

   where "myapp" is the application name.

3. Change directory to `myapp`, define an Agent:

    ```bash
    $ cd myapp
    $ runa generate agent MyAgent
    ```
   Run with `--help` or `-h` for options.

4. Run the agent:

    ```bash
    $ runa run MyAgent "..."
    ```

5. Follow the guides to start developing your application. You may find
   the following resources handy:
    * [Getting Started with Runa](docs/getting_started.md)
    * [Runa Guides](docs/guides.md)
    * [Runa Concepts](docs/concepts.md)

## Contributing

We encourage you to contribute to Runa! Please check out the
[Contributing to Runa guide](./CONTRIBUTING.md) for guidelines about how to proceed.

Trying to report a possible security vulnerability in Runa? Please
check out our [security policy](./SECURITY.md) for guidelines about how to proceed.

Everyone interacting in Runa is expected to follow the Runa [code of conduct](./CODE_OF_CONDUCT.md).

## License

Runa is released under the [MIT License](./LICENSE).
