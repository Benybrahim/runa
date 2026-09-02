# CLAUDE.md

Runa is an opinionated Python framework for agentic AI. Read `RUNA.md` before making architectural or implementation decisions — it defines the design principles and the order in which the framework evolves. Don't duplicate that content here; this file is the operational reference.

## Development workflow

Runa is built layer by layer, not feature by feature. For each unit of work:

1. Read `RUNA.md`, the relevant source, and relevant tests before changing anything. Don't assume the architecture.
2. Identify which layer the work belongs to. Don't implement later-layer functionality unless strictly necessary for the current one.
3. State the design briefly — the problem, the responsibility of the layer, the proposed API, why it fits Runa's philosophy. Keep it short.
4. Implement the smallest coherent version. No hypothetical extension points, no unused configuration, no speculative abstractions.
5. Write tests for observable behavior (public API, conventions, failure behavior) rather than implementation details.
6. Commit the completed logical unit with a message describing the architectural or functional change.

Don't stop at "it passes" — check the change is coherent with the rest of the framework before moving to the next task. Don't jump multiple layers ahead.

## Commands

- `make install` — uv sync
- `make format` — ruff format
- `make lint` / `make lint-fix` — ruff check
- `make typecheck` — pyright
- `make test` — pytest
- `make check` — format + lint + test
- `make example` — run `examples/hello.py`

Don't run lint or tests proactively — the user runs them manually.

## Conventions

- Python 3.14, managed with `uv`. Ruff config: line length 88, target `py314`, rules `E`, `F`, `I`.
- Tests live in `tests/`, mirroring `src/runa/`. Provider-dependent code should be testable without real API calls (see `tests/fakes.py`).
- Prefer clear names, small responsibilities, minimal dependencies. Avoid unnecessary inheritance hierarchies, metaprogramming, DSL complexity, god objects, and hidden behavior that makes debugging harder.

## Anti-patterns to reject on sight

- A default graph/node/edge execution model exposed as the primary API.
- A generic SDK where every concern (provider, executor, state store, tracer, retry policy) is a primitive the developer wires up manually.
- Abstractions justified by "we might need this later" rather than a concrete current problem.
- Rewriting working code without first identifying why the existing design can't evolve cleanly.

## Gotchas

- Target is Python 3.14: type annotations are lazily evaluated by default (PEP 649), so a missing import used only in a type hint won't fail at import time — it'll surface later under `typing.get_type_hints()` or similar introspection. Don't rely on that laziness; import what you annotate.