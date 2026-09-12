# Runa

The application framework for agentic AI.

Runa is opinionated: instead of a wide menu of configuration options, it gives you a small set
of primitives, with clear conventions for how they fit together — `Agent`, `Tool`, `Guardrail`,
`Subagent`, `Session`, `Memory`, `Knowledge`, `MCP Server`. Tracing and evaluation come built in,
not bolted on.

## Quickstart

```bash
uv venv --python 3.14
source .venv/bin/activate
uv add runa-ai

runa new myapp
cd myapp
runa generate agent AssistantAgent --model gpt-5.4-nano
runa chat assistant_agent
```

Fill in the API key for whichever model you use in `.env`, and you're running. Walk through it
step by step in [Getting Started](getting_started.md).

## Where to Go Next

* **New to Runa?** Start with [Getting Started](getting_started.md), then browse the
  [Guides](guides.md) for the topic you need.
* **Core Concepts.** [Agents](agents.md), [Tools](tools.md), [Guardrails](guardrails.md),
  [Subagents](subagents.md).
* **Running Agents.** [Sessions and Chat](sessions.md), [Memory](memory.md),
  [Knowledge](knowledge.md), [Cache](cache.md), [MCP Servers](mcp.md),
  [Human Approval](approval.md).
* **Testing and Evaluation.** [Evaluation](evaluation.md).
* **Observability.** [Tracing and Hooks](tracing.md).
* **Reference.** [Model Providers](models.md), [CLI Reference](cli.md).

## The Zen of Runa

```bash
python -c "from runa import this"
```
