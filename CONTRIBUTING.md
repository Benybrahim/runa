# Contributing to Runa

Runa is intentionally opinionated. Read [`RUNA.md`](./RUNA.md) before proposing
architectural or API changes — it defines the design principles and the order
in which the framework is meant to evolve. A change that doesn't fit those
principles is unlikely to be accepted regardless of how well it's implemented.

By participating, you're expected to follow the
[Code of Conduct](./CODE_OF_CONDUCT.md).

## Setup

```bash
make install   # uv sync
```

Requires Python 3.14, managed with [uv](https://docs.astral.sh/uv/).

## Before opening a PR

```bash
make check     # format + lint + test
```

Run this locally; it's the same bar a PR needs to clear. Individually:

```bash
make format      # ruff format
make lint         # ruff check (make lint-fix to auto-fix)
make typecheck    # pyright
make test         # pytest
```

If you touch `examples/`, also run `make examples` — those scripts call a
live model provider, so they need an API key in the environment (`OPENAI_API_KEY`
or `ANTHROPIC_API_KEY` depending on the provider used). `tests/test_examples.py`
exercises the same example code against a `FakeProvider`, so `make test` alone
still catches example rot without needing a key.

## Conventions

- Prefer clear names, small responsibilities, minimal dependencies.
- Avoid unnecessary inheritance hierarchies, metaprogramming, DSL complexity,
  god objects, and hidden behavior that makes debugging harder.
- Every convenience method needs an escape hatch to the primitive underneath
  it (manifesto §9) — see `Agent.run(executor=...)` for the pattern.
- New app-wide state is a real cost (manifesto §7); justify it against a
  per-call-site alternative before adding it, the way `config.py` does for
  the default `Provider`.

## Tests

New behavior needs a test. Provider-dependent code should be tested against
`tests/fakes.FakeProvider`, not a live API — see any file in `tests/` for the
pattern.

## Commit messages

Explain *why*, not just *what*. The diff already shows what changed.

## Proposing larger changes

Small, focused fixes can go straight to a pull request. For anything that
touches core architecture — a new abstraction, a change to the `Run`
lifecycle, a new top-level module — open an issue first and work through the
questions in [`RUNA.md`](./RUNA.md)'s "Runa Standard" (also summarized in
[`CLAUDE.md`](./CLAUDE.md#when-changing-architecture)) before writing code.
Discussing the shape of a change before implementing it saves rework on both
sides. See [`GOVERNANCE.md`](./GOVERNANCE.md) for how the project is run.
