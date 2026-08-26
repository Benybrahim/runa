# Runa Principles

Runa is an opinionated application framework for agentic AI.

Its goal is not to support every possible way of building agents.

Its goal is to provide a coherent, productive, and batteries-included way to build agentic applications.

These principles guide the design of Runa.

---

## 1. Convention Over Configuration

There should be one obvious way to do the common thing.

Runa should provide sensible defaults rather than requiring developers to configure every aspect of an agentic application.

If a developer repeatedly has to make the same decision, Runa should consider making that decision a convention.

---

## 2. The Agent Is an Application, Not a Loop

An agent is more than:

    prompt → model → tool → response

A production agentic application involves:

    Agent
    ├── Context
    ├── Tools
    ├── State
    ├── Execution
    ├── Policies
    ├── Persistence
    └── Evaluation

Runa should provide a coherent application model around these concerns.

---

## 3. Runs Are First-Class

An agent execution is not merely a function call.

Every execution should be represented by a `Run`.

A Run should eventually be:

- Inspectable
- Persistent
- Resumable
- Retryable
- Evaluatable

The Run is the fundamental unit of agent execution in Runa.

---

## 4. Simple by Default, Powerful by Escape Hatch

The common path should be extremely simple.

Advanced users must still be able to access lower-level behavior when necessary.

Complexity should be exposed when it is needed, not imposed on every developer.

---

## 5. Explicit Over Magical

Agentic systems are difficult enough to debug.

Runa should avoid abstractions that hide important behavior.

Developers should be able to understand:

- What the agent did
- Which tools it called
- What context it received
- What state changed
- Why an execution failed
- Where an execution is currently waiting

Convenience should never come at the cost of understanding.

---

## 6. Make the Common Agentic Path Boring

Production concerns should not require every team to reinvent infrastructure.

Runa should provide conventions for common concerns such as:

- Error handling
- Retries
- Persistence
- Checkpoints
- Observability
- Evaluation
- Human approval

The framework should make these concerns predictable rather than novel.

---

## 7. Runtime Is an Implementation Detail

Runa owns the application model, not the underlying model provider or agent runtime.

The application should not be tightly coupled to one provider.

Runa should be able to operate above different runtimes and providers without changing the fundamental application model.

The framework should build on existing protocols and infrastructure rather than unnecessarily replacing them.

---

## 8. Evaluation Is Development

Agent behavior is probabilistic.

Traditional unit tests alone are insufficient.

Evaluation should be part of the normal development lifecycle:

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

A production failure should be easy to turn into a regression case.

---

## 9. Opinionated Core, Open Ecosystem

Runa's core should remain small and strongly opinionated.

Not every useful integration belongs in the framework.

Provider-specific functionality, integrations, and specialized behavior should live outside the core whenever possible.

The core should define the application model.

The ecosystem can define everything around it.

---

## 10. Don't Abstract What You Haven't Built

Runa should be discovered through real applications rather than designed entirely on paper.

We prefer:

- Real use cases over theoretical abstractions
- Small APIs over configuration systems
- Working examples over architectural diagrams
- Concrete implementations over premature interfaces
- Proven patterns over speculative features

If we have not encountered the problem, we should be cautious about designing an abstraction for it.

---

## 11. Developer Experience Is a Feature

Runa exists to make developers more productive.

The quality of the API matters as much as the underlying implementation.

A good Runa API should feel:

- Obvious
- Predictable
- Concise
- Discoverable
- Consistent

When an API requires extensive documentation to explain its basic usage, the API should be questioned first.

---

## 12. Boring Infrastructure, Interesting Applications

Runa should make infrastructure disappear without making execution disappear.

Developers should spend their time building agentic applications, not repeatedly implementing:

- Checkpoint stores
- Retry systems
- Execution tracking
- Background workers
- Evaluation pipelines
- Tool plumbing

The framework should handle the boring parts.

The application should contain the interesting parts.

---

## Design Rule

When considering a new feature, ask:

> Does this make the common path for building an agentic application significantly simpler?

If not, it probably does not belong in Runa's core.

---

## Governance

Runa is an opinionated project.

The maintainers are responsible for protecting its architectural direction and have final authority over the core API, architecture, and roadmap.

Contributions are welcome, but contribution volume is not a goal by itself.

A contribution is valuable when it strengthens Runa's existing philosophy.

Runa should not become a collection of every useful agentic pattern.

---

## The North Star

Runa should make building an agentic application feel as natural as building a web application with a mature application framework.

The goal is not maximum flexibility.

The goal is maximum productivity within a coherent set of strong opinions.