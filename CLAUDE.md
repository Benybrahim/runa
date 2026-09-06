# CLAUDE.md

Runa is an opinionated Python framework for agentic AI.

Read [RUNA.md](./RUNA.md) before making architectural or implementation decisions. It defines Runa's core principles and design direction.

When a decision requires more context:

* [docs/concepts.md](./docs/concepts.md) defines Runa's core vocabulary, including the Tool interface Agents use to act on the world.
* [docs/getting_started.md](./docs/getting_started.md) describes the intended developer experience.
* [docs/guides.md](./docs/guides.md) contains practical patterns.
* [docs/cli.md](./docs/cli.md) is the `runa` command-line reference.

Do not duplicate the philosophy from these documents here. This file is the operational reference for development.

## Commands

* `make install`: uv sync
* `make format`: ruff format
* `make lint` / `make lint-fix`: ruff check
* `make typecheck`: pyright (not yet wired into `make check`)
* `make test`: pytest
* `make check`: format + lint + test
* `make hello`: run `examples/hello.py`
* `make examples`: run every example in `examples/`

## Development Principles

* Read the relevant Runa documentation before changing architecture or introducing a new abstraction.
* Prefer the smallest design that satisfies the existing application need.
* Keep the common path simple; advanced behavior should be opt-in.
* Preserve Runa's core model, the Agent-Run-Execution (ARE) pattern: **Agents declare behavior; Execution progresses it; Runs persist it.**
* Keep provider, persistence, background, observability, and evaluation infrastructure outside the core primitives.
* Do not introduce graphs, orchestration abstractions, or agent-specific machinery unless ordinary application code cannot express the problem clearly.
* Keep state lifetimes explicit: Run state, Conversation state, and Domain state are distinct.
* Keep capabilities and authority explicit. Intelligence does not imply authority.
* Prefer existing abstractions over creating new ones. Add a new abstraction only when the codebase reveals a recurring problem.
* Preserve escape hatches. Convenience APIs must not prevent direct access to underlying Runa primitives or integrations.
* Do not use ""—"" in any file.

## Code Conventions

* Python 3.14, managed with `uv`.
* Ruff config: line length 88, target `py314`, rules `E`, `F`, `I`.
* Prefer clear names, small responsibilities, minimal dependencies.
* Avoid unnecessary inheritance hierarchies, metaprogramming, DSL complexity, god objects, and hidden behavior that makes debugging harder.
* Keep dependencies flowing outward from core primitives toward infrastructure implementations.
* Provider-specific concepts must remain inside provider adapters.
* Tests should verify deterministic invariants; evaluations should measure probabilistic agent behavior.

## When Changing Architecture

Before introducing a new core abstraction, ask:

1. Is this a recurring application problem?
2. Does an existing Runa concept already express it?
3. Does it belong naturally to an Agent, Execution, Run, State, or Capability?
4. Does it simplify the common case?
5. Does it preserve the architectural boundaries?
6. Does it preserve an escape hatch?
7. Can the behavior be tested and observed through the existing Run model?

If the answer is mostly no, do not add the abstraction.