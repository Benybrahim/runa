# Runa

The application framework for agentic AI.

Runa is opinionated: for every primitive — Agent, Tool, Guardrail,
Subagent, Session, Memory, MCP Server, Model, Hooks, Test, Eval — there's
exactly one sanctioned shape, not a menu of equivalent options. Less
configuration, more convention.

```python
from runa import Agent, tool


@tool
def get_weather(city: str) -> str:
    """Return the current weather for a city."""
    ...


class SupportAgent(Agent):
    name = "support_agent"
    instructions = "You help customers troubleshoot their orders."
    model = "claude-sonnet-5"
    tools = [get_weather]
```

## Where to Start

New to Runa? Read [Getting Started](getting_started.md) end to end — it
scaffolds an app and walks through tools, guardrails, subagents, chat, and
testing in one pass.

Already up and running? [Guides](guides.md) indexes every topic below by
area, to jump straight to what you need.

## Core Concepts

* **[Agents](agents.md)** — the `Agent` class, its attributes, and running it.
* **[Tools](tools.md)** — exposing functions to the model with `@tool`.
* **[Guardrails](guardrails.md)** — checking input/output with `@guardrail`.
* **[Subagents](subagents.md)** — composing agents with `.handoff` and `.delegate`.

## Running Agents

* **[Sessions and Chat](sessions.md)** — persisting conversation history.
* **[Memory](memory.md)** — long-term, semantic memory across conversations.
* **[Cache](cache.md)** — a minimal get/set/delete/clear cache.
* **[MCP Servers](mcp.md)** — connecting to external tool servers over MCP.
* **[Human Approval](approval.md)** — gating sensitive tool calls.

## Testing, Evaluation & Observability

* **[Testing](testing.md)** — deterministic checks with `runa test`.
* **[Evaluation](evaluation.md)** — behavioral evals with `runa eval`.
* **[Tracing and Hooks](tracing.md)** — what's recorded for every run.

## Reference

* **[Model Providers](models.md)** — which model string picks which provider.
* **[CLI Reference](cli.md)** — every `runa` command in one place.
