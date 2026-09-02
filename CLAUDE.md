# CLAUDE.md

Runa is an opinionated Python framework for agentic AI. 

Read [RUNA.md](./RUNA.md) before making architectural or implementation decisions — it defines the design principles and the order in which the framework evolves. Don't duplicate that content here; this file is the operational reference.

## Commands

- `make install` — uv sync
- `make format` — ruff format
- `make lint` / `make lint-fix` — ruff check
- `make typecheck` — pyright
- `make test` — pytest
- `make check` — format + lint + test
- `make hello` — run `examples/hello.py`
- `make examples` — run every example in `examples/`

## Conventions

- Python 3.14, managed with `uv`. Ruff config: line length 88, target `py314`, rules `E`, `F`, `I`.
- Prefer clear names, small responsibilities, minimal dependencies. Avoid unnecessary inheritance hierarchies, metaprogramming, DSL complexity, god objects, and hidden behavior that makes debugging harder.