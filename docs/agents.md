# Agents

An `Agent` is a Python class. Its class attributes are its entire
configuration — there's no separate config object to build.

```python
from runa import Agent


class SupportAgent(Agent):
    name = "support_agent"
    instructions = "You help customers troubleshoot their orders."
    model = "claude-sonnet-5"
```

## Attributes

| Attribute      | Default          | Meaning                                            |
|----------------|------------------|-----------------------------------------------------|
| `name`         | required         | The agent's identity: traces, handoffs, `runa chat` all key off it |
| `instructions` | `None`           | A system prompt string, or a `(context) -> str` callable |
| `model`        | `"gpt-5.4-nano"` | Which model to call — see [Model Providers](models.md) |
| `model_settings` | `ModelSettings()` | Temperature, max tokens, etc. |
| `tools`        | `[]`             | `@tool`-decorated functions — see [Tools](tools.md) |
| `subagents`    | `[]`             | Other agents to hand off or delegate to — see [Subagents](subagents.md) |
| `guardrails`   | `[]`             | Input/output checks — see [Guardrails](guardrails.md) |
| `mcp`/`mcp_servers` | `[]`        | MCP servers whose tools this agent can call — see [MCP Servers](mcp.md) |
| `output_type`  | `None`           | A type the final output must parse as |
| `hooks`        | `None`           | An `AgentHooks` instance scoped to this agent |

`name` is the only required attribute. Everything else has a sane default,
in the spirit of convention over configuration.

## Instructions as a Function

`instructions` can be a plain string, or a function of one argument — the
`context` passed to `run`/`run_sync` — resolved fresh on every call:

```python
from dataclasses import dataclass


@dataclass
class Context:
    user_name: str


def instructions(context: Context) -> str:
    return f"You are a friendly assistant helping {context.user_name}."


class Assistant(Agent):
    name = "assistant"
    instructions = instructions


Assistant().run_sync("Hi", context=Context(user_name="Ada"))
```

`context` is never sent to the model. It's plumbed through to
`instructions`, tools, and guardrails as-is, so it's the place to put
per-run data (a user id, a tenant, a request-scoped client) without
smuggling it through global state.

## Running an Agent

```python
agent = SupportAgent()
run = agent.run_sync("My order hasn't arrived.")
print(run.output)
```

`run_sync`/`run`/`run_streamed` all append the turn to `agent.history`, so
the next call on the same instance continues the conversation. Pass
`session=` instead to persist history to `runa.db` — see
[Sessions and Chat](sessions.md).

`run`/`run_sync` return a `Run`:

* `run.output` — the final output (`None` if the run errored)
* `run.status` — `"completed"` or `"error"`
* `run.error` — the error message, when `status == "error"`
* `run.usage` — this call's token usage
* `run.trace` — the full span tree for this call, see [Tracing](tracing.md)

A guardrail tripwire or a runtime error (`MaxTurnsExceeded`, a model error)
is caught and reported as `status="error"` rather than raised —
`agent.history` is left unchanged, since the turn never completed.

`run_streamed` instead yields `StreamEvent`s as the model responds, and
updates `agent.history` only once the stream is fully consumed.

## Usage

```python
agent.last_usage  # tokens used by the most recent call
agent.usage  # accumulated across every call on this instance
```

Both are populated regardless of whether the run succeeded, used a
`session`, or passed `hooks`.

## Visualizing an Agent

`agent.graph` renders the agent, its tools, and its handoffs as a Graphviz
diagram (inline in Jupyter; `.render(path)` to save, `.source` for raw
DOT). Needs the system `dot` binary to actually rasterize an image.
