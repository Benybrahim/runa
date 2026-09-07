# CLAUDE.md

Runa is an opinionated Python framework for agentic AI.

## Commands

* `make install`: uv sync
* `make format`: ruff format
* `make lint` / `make lint-fix`: ruff check
* `make typecheck`: pyright (not yet wired into `make check`)
* `make test`: pytest
* `make check`: format + lint + test

## Development Principles

- Zen of Python: `import this`
- Less is better than more.
- Don't write comments, code should explain itself.

## Code Conventions

* Python 3.14, managed with `uv`.
* Ruff config: line length 100, target `py314`, rules `E`, `F`, `I`. `B`, `SIM`, `UP`

