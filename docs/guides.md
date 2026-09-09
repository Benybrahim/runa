# Runa Guides

These guides assume you've read [Getting Started with Runa](getting_started.md).
Each one stands alone — read whichever covers what you're building today.

## Start Here

* **[Getting Started with Runa](getting_started.md).**
  Install Runa, scaffold an app, and run your first agent.

## Core Concepts

* **[Agents](agents.md).**
  The `Agent` class: attributes, `instructions`, `run`/`run_sync`/`run_streamed`,
  history, usage, and context.

* **[Tools and Guardrails](tools_and_guardrails.md).**
  Exposing functions to the model with `@tool`, and checking input/output
  with `@guardrail`.

* **[Subagents](subagents.md).**
  Composing agents with `.handoff` and `.delegate`.

## Running Agents

* **[Sessions and Chat](sessions.md).**
  Persisting conversation history with `SQLiteSession`, and `runa chat`.

* **[MCP Servers](mcp.md).**
  Connecting to external tool servers over MCP.

* **[Human Approval](approval.md).**
  Gating sensitive tool calls behind human approval, and how that differs
  from a guardrail.

## Testing and Evaluation

* **[Testing and Evaluating Agents](testing_and_evaluation.md).**
  Deterministic tests with `runa test`, behavioral evals with `runa eval`.

## Observability

* **[Tracing and Hooks](tracing.md).**
  What gets recorded for every run, `runa traces`, and lifecycle hooks.

## Reference

* **[Model Providers](models.md).**
  Which model string picks which provider, and where its API key lives.

* **[CLI Reference](cli.md).**
  Every `runa` command in one place.
