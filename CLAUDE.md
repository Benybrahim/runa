# CLAUDE.md

Runa is an opinionated Python framework for agentic AI.

Read [RUNA.md](./RUNA.md) before making architectural or implementation decisions. It defines Runa's core principles and design direction.

When a decision requires more context:

* [docs/manifesto.md](./docs/manifesto.md) explains why Runa takes this approach.
* [docs/concepts.md](./docs/concepts.md) defines Runa's core vocabulary.
* [docs/architecture.md](./docs/architecture.md) defines the technical architecture, boundaries, and invariants.
* [docs/getting_started.md](./docs/getting_started.md) describes the intended developer experience.
* [docs/guides.md](./docs/guides.md) contains practical patterns.
* [BRAND.md](personal/BRAND.md) defines Runa's identity: positioning, voice, terminology, and visual direction. Read it before writing README/docs copy, CLI-facing text, or anything visual.

Do not duplicate the philosophy from these documents here. This file is the operational reference for development.

## Commands

* `make install`: uv sync
* `make format`: ruff format
* `make lint` / `make lint-fix`: ruff check
* `make test`: pytest
* `make check`: format + lint + test
* `make hello`: run `examples/hello.py`
* `make examples`: run every example in `examples/`

## Development Principles

* Read the relevant Runa documentation before changing architecture or introducing a new abstraction.
* Prefer the smallest design that satisfies the existing application need.
* Keep the common path simple; advanced behavior should be opt-in.
* Preserve Runa's core model: **Agents define behavior; Runs define execution.**
* Keep provider, persistence, background, observability, and evaluation infrastructure outside the core primitives.
* Do not introduce graphs, orchestration abstractions, or agent-specific machinery unless ordinary application code cannot express the problem clearly.
* Prefer Agent behavior and lifecycle hooks before introducing a custom `Strategy`.
* Keep state lifetimes explicit: Run state, Conversation state, and Application state are distinct.
* Keep Context distinct from State: Context is what the Agent is given; State is what the application/runtime owns.
* Keep capabilities and authority explicit. Intelligence does not imply authority.
* Prefer existing abstractions over creating new ones. Add a new abstraction only when the codebase reveals a recurring problem.
* Preserve escape hatches. Convenience APIs must not prevent direct access to underlying Runa primitives or integrations.
* Do not use ""—"" in any file.

## Code Conventions

* Python 3.14, managed with `uv`.
* Ruff config: line length 88, target `py314`, rules `E`, `F`, `I`.
* Prefer clear names, small responsibilities, minimal dependencies.
* Avoid unnecessary inheritance hierarchies, metaprogramming, DSL complexity, god objects, and hidden behavior that makes debugging harder.
* Prefer explicit behavior over surprising magic.
* Keep dependencies flowing outward from core primitives toward infrastructure implementations.
* Provider-specific concepts must remain inside provider adapters.
* Tests should verify deterministic invariants; evaluations should measure probabilistic agent behavior.

## When Changing Architecture

Before introducing a new core abstraction, ask:

1. Is this a recurring application problem?
2. Does an existing Runa concept already express it?
3. Does it belong naturally to an Agent, Run, Context, State, or Capability?
4. Does it simplify the common case?
5. Does it preserve the architectural boundaries?
6. Does it preserve an escape hatch?
7. Can the behavior be tested and observed through the existing Run model?

If the answer is mostly no, do not add the abstraction.