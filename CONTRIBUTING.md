# Contributing to Runa

Thank you for your interest in Runa.

Runa is an open-source project with a strong architectural vision.

We welcome contributions, but we intentionally keep the core framework opinionated.

The goal is not to accept every possible feature.

The goal is to build the best possible developer experience for a particular way of building agentic applications.

Before contributing, please read [RUNA.md](RUNA.md).

---

## Development Philosophy

Runa follows a simple development loop:

1. Problem
2. Design
3. Developer-facing API
4. Test
5. Implementation
6. Real-world validation
7. Pull request
8. CI
9. Review

### API Before Implementation

For new features, start with how the developer should use them.

For example:

```python
run = agent.run(...)

run.pause()

# Later

run.resume()
````

is a better starting point than designing internal classes first:

```python
class CheckpointManager:
    ...
```

The public API should drive the implementation.

Avoid designing large internal abstractions before validating their usage.

### Don't Abstract Prematurely

Prefer:

* Real use cases over theoretical abstractions
* Small APIs over configuration systems
* Working examples over architectural diagrams
* Concrete implementations over premature interfaces
* Proven patterns over speculative features

If we have not encountered the problem, we should be cautious about designing an abstraction for it.

### Real-World Validation

New concepts should be validated through realistic usage.

Before expanding an abstraction, use it in an actual example or application and ask:

> Would I actually want to build software this way?

If the API feels awkward, improve the API before adding more implementation.

---

# Coding Conventions

Coding conventions apply to **all Runa code**, not only agent-specific functionality.

They should reinforce the principles in [`RUNA.md`](RUNA.md).

The objective is not to enforce style for its own sake.

The objective is to produce code that is:

* Simple
* Explicit
* Predictable
* Readable
* Easy to change
* Consistent with Runa's architecture

## Simplicity

Prefer the simplest implementation that clearly solves the problem.

Avoid:

* Unnecessary abstractions
* Deep inheritance hierarchies
* Configuration for uncommon cases
* Generic frameworks inside the framework
* Clever code that hides behavior

If a straightforward implementation works, prefer it.

## Explicitness

Code should make important behavior easy to understand.

Prefer explicit control flow over abstractions that obscure what is happening.

Especially avoid hiding:

* State changes
* Errors
* External calls
* Side effects
* Lifecycle transitions

Convenience should not make behavior mysterious.

## Small APIs

Keep public APIs small.

Every public class, function, option, and configuration parameter creates a long-term maintenance commitment.

Before adding one, ask:

> Does this belong to the core application model?

If the answer is unclear, keep it internal until the need is proven.

## Naming

Use names that describe concepts rather than implementation details.

```python
class Run:
    ...

def resume():
    ...

state = ...
```

Avoid names that unnecessarily encode implementation choices.

Use standard Python naming conventions:

* `PascalCase` for classes
* `snake_case` for functions and variables
* `UPPER_SNAKE_CASE` for constants

## Type Hints

Public APIs should be typed.

Prefer precise types over `Any` where practical.

Types should communicate the intended contract rather than merely satisfy a type checker.

## Dependencies

Keep the dependency footprint small.

Before adding a dependency, ask:

1. Can the standard library solve this?
2. Does the dependency provide substantial value?
3. Does it introduce unnecessary coupling?
4. Does Runa actually need to own this functionality?

Avoid dependencies that solve only small or isolated problems.

## Abstraction Boundaries

Abstractions should correspond to meaningful concepts in Runa.

Do not create an abstraction simply because:

* Two classes share some code
* A pattern might be useful later
* A future provider might need it
* It makes the architecture look cleaner

Prefer duplication over a premature abstraction when the correct abstraction is not yet clear.

## Internal vs Public APIs

Keep implementation details internal unless they are intentionally part of the public API.

A small public surface is preferable to exposing every useful internal component.

When something becomes public, treat it as a long-term commitment.

## Errors

Errors should be explicit and actionable.

Avoid catching exceptions merely to hide complexity.

Do not silently recover from failures unless that behavior is an intentional part of the API.

## Documentation

Document behavior that users need to understand.

Avoid documenting implementation details that users should not depend on.

Public APIs should have concise documentation when their behavior is not obvious from their names and signatures.

## Formatting and Tooling

Use Ruff for formatting and linting:

```bash
ruff format .
ruff check .
```

Run tests with:

```bash
pytest
```

Static type checking should also pass once the project's type checker is configured.

Tooling should automate consistency rather than create unnecessary process.

---

# Testing

New behavior should normally include tests.

Tests should focus on behavior and public contracts rather than implementation details.

Prefer:

```python
assert result.output == expected
```

over tests tightly coupled to internal class structure.

## Test Levels

Use the appropriate level of testing:

* Unit tests for isolated logic
* Integration tests for interactions between Runa components
* End-to-end tests for important user-facing workflows

Keep the majority of tests fast and deterministic.

## Deterministic Tests

Avoid making the entire test suite dependent on external model calls or network services.

Use mocks, fixtures, fake runtimes, or deterministic test implementations where appropriate.

Model-based evaluation can be introduced separately when deterministic assertions are insufficient.

---

# Architecture Decisions

Significant architectural decisions should be documented in:

```text
docs/decisions/
```

Use an Architecture Decision Record (ADR) for decisions affecting:

* Core abstractions
* Public APIs
* Runtime architecture
* Persistence
* Execution semantics
* Major dependencies
* Long-term application architecture

A typical ADR should contain:

```markdown
# ADR XXXX: Title

## Context

What problem are we solving?

## Decision

What are we choosing?

## Why

Why did we choose it?

## Alternatives

What alternatives did we consider?

## Consequences

What does this decision make easier or harder?

## Status

Proposed / Accepted / Superseded
```

Significant architectural decisions should be discussed before implementation when they can substantially affect the project.

---

# Dependencies

Keep the core dependency footprint small.

Before adding a dependency, consider:

1. Can the standard library solve the problem?
2. Does the dependency provide substantial value?
3. Is it actively maintained?
4. Does it introduce unnecessary coupling?
5. Does Runa actually need to own this functionality?

Prefer boring, well-established dependencies over unnecessary complexity.

---

# Pull Requests

Pull requests should be focused and easy to review.

A pull request should explain:

1. What problem does this solve?
2. Why does it belong in Runa?
3. What is the proposed API?
4. How was it tested?
5. Does it change an existing public API?

Avoid combining unrelated refactors with feature changes.

## Pull Request Checklist

Before submitting:

* [ ] Tests added or updated
* [ ] Tests pass
* [ ] Ruff formatting passes
* [ ] Ruff linting passes
* [ ] Type checking passes
* [ ] Documentation updated when necessary
* [ ] Public API changes are intentional
* [ ] Changelog updated when appropriate

---

# Feature Requests

Describe the problem rather than only the desired implementation.

Good:

> Agent executions cannot currently resume after a process restart.

Less useful:

> Add a `CheckpointManager` class.

The first describes the problem.

The second prematurely commits to an implementation.

---

# What Belongs in Core?

Runa's core should contain concepts that are fundamental to its application model.

Before adding something, ask:

> Would most Runa applications benefit from this?

If not, consider:

* An external package
* An integration
* A plugin
* Application-level code

The core should remain small.

---

# What We Will Say No To

A feature may be rejected even if it is useful.

Examples include features that:

* Add significant configuration for uncommon cases
* Duplicate functionality already provided by existing infrastructure
* Introduce unnecessary abstractions
* Make the common path more complicated
* Couple Runa to a specific provider without strong justification
* Support a niche architecture that does not belong in the core
* Conflict with the principles in `RUNA.md`

A rejection is not a judgment on the idea.

It may simply mean that the feature does not belong in Runa's core.

---

# Commit Conventions

Use concise, descriptive commit messages.

Preferred format:

```text
<type>: <description>
```

Examples:

```text
feat: add durable runs
fix: preserve tool errors
docs: explain run lifecycle
test: add tool execution tests
refactor: simplify runtime interface
chore: update dependencies
```

Common types:

* `feat` — new functionality
* `fix` — bug fix
* `docs` — documentation
* `test` — tests
* `refactor` — code restructuring without behavior change
* `chore` — maintenance

Keep the first line concise and focused.

---

# Versioning

Runa follows Semantic Versioning.

Before `1.0.0`, the public API may change as the framework evolves.

Breaking changes should be clearly documented in the changelog.

---

# Local Development

Create a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
```

Install the project in editable mode:

```bash
pip install -e ".[dev]"
```

Run the local checks:

```bash
ruff format .
ruff check .
pytest
```

Type checking should also pass once the project's type checker is configured.

---

# Community

Discussions are welcome.

Strong disagreement is acceptable and often useful.

Keep discussions focused on:

* The problem
* The tradeoffs
* The developer experience
* Runa's principles

The maintainers have final authority over the direction of the core project.

---

# A Note to Contributors

Runa is intentionally opinionated.

You do not need to agree with every design decision to contribute.

However, contributions should work within the project's overall philosophy.

If you want to experiment with a fundamentally different architecture, consider building an external package or fork rather than expanding the Runa core.

The goal is a small, coherent framework — not the largest possible one.
