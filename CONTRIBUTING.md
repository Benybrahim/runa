# Contributing to Runa

Thank you for your interest in Runa.

Runa is an open-source project with a strong architectural vision.

We welcome contributions, but we intentionally keep the core framework opinionated.

The goal is not to accept every possible feature.

The goal is to build the best possible developer experience for a particular way of building agentic applications.

Before contributing, please read [RUNA.md](RUNA.md).

---

## Before You Start

For significant changes, open an issue or discussion before implementing the feature.

This is especially important for:

- New core abstractions
- Public API changes
- New dependencies
- Runtime architecture
- Persistence
- Workflow primitives
- Changes to the execution model

Small bug fixes and documentation improvements generally do not require prior discussion.

---

## Design Before Code

For architectural changes, start with the developer experience.

Describe how you believe the feature should be used before describing how it should be implemented.

For example:

```python
run = agent.run(...)
run.pause()

# Later

run.resume()
```

is more useful as a starting point than:
```python
class CheckpointManager:
    ...
```

The public API should drive the implementation.