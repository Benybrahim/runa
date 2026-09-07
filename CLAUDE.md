# CLAUDE.md

Runa is an opinionated Python framework for agentic AI.

## Commands

* `make install`: uv sync
* `make format`: ruff format
* `make lint` / `make lint-fix`: ruff check
* `make typecheck`: pyright
* `make test`: pytest
* `make check`: format + lint + test

## Zen of Python

- `import this`
- Less is better than more.
- Files should tell a story from top to bottom. Start with the most important concepts and progressively move into details.

## Code Conventions

* Python 3.14, managed with `uv`.
* Ruff config: line length 100, target `py314`, rules `E`, `F`, `I`. `B`, `SIM`, `UP`, `D`.
* Use `Sphinx/reST` without `type` and `rtype` for docstrings.
* Always give oneliner commit message: `feat`, `fix`, `docs`, `test`, `refactor`.
* Always pass `make check`.
* Add Tests as needed. Test one behavior, prefer real objects, mock boundaries, and assert outcomes over implementation.


