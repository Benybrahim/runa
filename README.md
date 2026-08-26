# Runa

> The application framework for agentic AI.

Runa is an opinionated Python framework for building production agentic applications.

Inspired by the philosophy of Ruby on Rails, Runa aims to bring **convention over configuration, batteries included, and a strong application model** to agentic software.

Runa is not another model SDK or agent runtime.

It aims to provide the **application layer above them**.

## Why Runa?

Building a serious agentic application today often means assembling and integrating many separate pieces:

- Agent runtimes
- Model providers
- Tools
- Context management
- State and persistence
- Memory
- Workflows
- Background jobs
- Human approval
- Observability
- Evaluations
- Deployment infrastructure

Existing agent SDKs are useful, but they primarily focus on the **agent execution layer**.

Runa focuses on the larger question:

> **How should an agentic application be structured and built?**

The goal is to make the common path simple while providing the infrastructure needed to grow from a prototype into a production application.

## Philosophy

Runa is strongly opinionated.

It does not aim to support every possible way of building agents. Instead, it provides a small set of conventions and primitives that represent one coherent approach to agentic application development.

### 1. Convention Over Configuration

There should be one obvious way to do the common thing.

Runa provides sensible defaults instead of requiring developers to configure every aspect of agent execution.

### 2. The Agent Is an Application, Not a Loop

An agent is more than:

```text
prompt → model → tool → response
````

A production agentic application involves:

```text
Agent
├── Context
├── Tools
├── State
├── Execution
├── Policies
├── Persistence
└── Evaluation
```

Runa provides a coherent model for these components.

### 3. Runs Are First-Class

An agent execution is not just a function call.

A `Run` represents the lifecycle of an agent execution and should eventually be:

* Inspectable
* Persistent
* Resumable
* Retryable
* Evaluatable

```text
Run
├── Input
├── Context
├── State
├── Steps
├── Model calls
├── Tool calls
├── Errors
├── Checkpoints
└── Output
```

### 4. Simple by Default, Powerful by Escape Hatch

The common path should require very little configuration.

Advanced developers should still be able to access lower-level behavior when necessary.

### 5. Explicit Over Magical

Agentic systems are difficult enough to debug.

Runa should make execution understandable rather than hiding important behavior behind excessive abstraction.

### 6. Make the Common Agentic Path Boring

Production concerns such as:

* Retries
* State
* Persistence
* Error handling
* Observability
* Evaluation

should not require every team to reinvent the same infrastructure.

### 7. Runtime Is an Implementation Detail

Runa should not depend on a single model provider or agent runtime.

The application model should remain stable even as underlying technologies change.

```text
                    Runa
                      │
            Agentic Application
                      │
        ┌─────────────┼─────────────┐
        │             │             │
     OpenAI       Anthropic      Other
     Runtime       Runtime      Runtimes
```

### 8. Evaluation Is Development

Agent behavior is probabilistic.

Testing cannot stop at traditional unit tests.

Runa treats evaluation as part of the development lifecycle:

```text
Build
  ↓
Run
  ↓
Evaluate
  ↓
Improve
  ↓
Regression Test
  ↓
Deploy
```

### 9. Opinionated Core, Open Ecosystem

Runa's core should remain small and strongly opinionated.

Integrations and provider-specific functionality should live outside the core whenever possible.

### 10. Don't Abstract What You Haven't Built

Runa should be discovered through real applications rather than designed entirely on paper.

We prefer:

* Real use cases over theoretical abstractions
* Small APIs over configuration systems
* Working examples over architectural diagrams
* Concrete implementations over premature interfaces

## Quick Start

> **Early development:** The API is currently unstable and subject to change.

```python
from runa import Agent, tool


@tool
def get_weather(city: str) -> str:
    return f"{city}: sunny"


agent = Agent(
    name="weather",
    tools=[get_weather],
)

result = agent.run("What's the weather in Tokyo?")

print(result.output)
```

The goal is for this simple interface to grow into a complete production application without requiring developers to replace the underlying architecture.

## Core Concepts

Runa is intentionally starting with a small number of primitives.

### Agent

The application-level agent.

```python
agent = Agent(
    name="support",
    tools=[search_customer, issue_refund],
)
```

### Tool

A capability an agent can invoke.

```python
@tool
def search_customer(customer_id: str):
    ...
```

### Run

A single execution of an agent.

Runs will eventually provide durable execution, inspection, checkpoints, retries, and resumption.

### Runtime

The underlying execution implementation.

```text
Runa
  ↓
Runtime
  ↓
Model / Agent SDK
```

The runtime should remain replaceable.

## What Runa Is Not

Runa is not intended to be:

* Another LLM wrapper
* Another prompt management library
* Another multi-agent framework
* A replacement for MCP
* A replacement for A2A
* A model provider
* A framework that tries to abstract every possible agent architecture

Runa should build on existing infrastructure wherever possible.

## Project Status

Runa is currently an early-stage project.

The first milestone is intentionally small:

* [x] Initial project structure
* [x] Core `Agent` abstraction
* [x] Core `Tool` abstraction
* [x] `Run` abstraction
* [x] Runtime abstraction
* [ ] Working model runtime
* [ ] End-to-end agent execution
* [ ] Tool calling
* [ ] Basic tests
* [ ] CLI
* [ ] Durable execution
* [ ] Context and state
* [ ] Evaluation system
* [ ] Additional runtimes

The API will change significantly before the first stable release.

## Roadmap

### Phase 1 — Golden Path

Make the basic agent experience excellent:

```text
Agent
  ↓
Run
  ↓
Runtime
  ↓
Model
  ↓
Tools
```

The first goal is not to support every agent architecture.

The goal is to make one common agentic application extremely easy to build.

### Phase 2 — Durable Runs

Introduce:

* Persistent runs
* Checkpoints
* Resume
* Retries
* Error handling
* Execution inspection

This is where Runa begins to move beyond a traditional agent SDK.

### Phase 3 — Context and State

Introduce a coherent application-level model for:

* User context
* Conversation context
* Runtime context
* Application state
* Tool results
* Persistent state

### Phase 4 — Application Lifecycle

Introduce application-level primitives such as:

* Jobs
* Workflows
* Human approval
* Policies
* Scheduling
* Background execution

### Phase 5 — Evaluation and Improvement

Make evaluation a native part of the Runa development lifecycle.

```text
Production Run
      ↓
Evaluation
      ↓
Failure
      ↓
Regression Case
      ↓
Fix
      ↓
Evaluation
```

### Phase 6 — Production Infrastructure

Provide conventions and primitives for:

* Observability
* Distributed execution
* Persistence
* Deployment
* Background workers
* Production operations

### Phase 7 — Runtime Ecosystem

Support additional underlying runtimes without changing the Runa application model.

## Development

Clone the repository:

```bash
git clone <repository-url>
cd runa
```

Create a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
```

Install in editable mode:

```bash
pip install -e ".[dev]"
```

Run tests:

```bash
pytest
```

## Design Rule

When considering a new feature, ask:

> **Does this make the common path for building an agentic application significantly simpler?**

If not, it probably does not belong in Runa's core.

## Long-Term Vision

Traditional web development evolved from assembling low-level infrastructure into using application frameworks such as Ruby on Rails.

Agentic software is going through a similar transition.

Today, developers often assemble:

```text
Models
+
Agent SDKs
+
Tools
+
State
+
Memory
+
Workflows
+
Observability
+
Evaluation
+
Infrastructure
```

Runa explores what the equivalent **application framework for agentic software** could look like.

```text
Traditional Applications

Rails
  ↓
Web Application
  ↓
Database / Infrastructure


Agentic Applications

Runa
  ↓
Agentic Application
  ↓
Agent Runtime
  ↓
Models / Tools / Protocols
```

The underlying technologies will continue to evolve.

**Runa's goal is to provide a stable, opinionated application layer above them.**

---

## License

[License TBD]

```
```
