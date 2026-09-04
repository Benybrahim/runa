# Governance

Runa is maintained as an open-source project. This document describes how it's run today — it will evolve as the project and its community grow, rather than pre-committing to process the project doesn't need yet.

## Maintainers

Maintainers are responsible for Runa's technical direction and overall project quality: reviewing and merging contributions, triaging issues, and deciding what does and doesn't fit the framework's design.

## Design principles come first

Runa is intentionally opinionated, not a collection of independently useful features. [`RUNA.md`](RUNA.md) defines the principles maintainers use to evaluate changes — coherence with the Run model, convention over configuration, escape hatches preserved. A change that doesn't fit those principles is unlikely to be accepted regardless of implementation quality.

## Proposing changes

Contributors are welcome to propose changes through issues, discussions, and pull requests using whatever mechanisms the repository currently supports. Small, focused changes (bug fixes, documentation, incremental improvements) can go straight to a pull request.

**Significant architectural changes** — a new core abstraction, a change to the `Run` lifecycle, a new top-level module — should be discussed in an issue before implementation. See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the questions maintainers ask when evaluating this kind of change.

## Compatibility

Runa's public API is deliberate, not accidental. Breaking changes are made carefully, and prioritized over accumulating configuration flags or backward-compatibility shims that would compromise the framework's coherence.

## Priorities

When priorities conflict, Runa favors coherence over raw feature count: a smaller framework where every part fits together beats a larger one assembled from independently reasonable pieces.
