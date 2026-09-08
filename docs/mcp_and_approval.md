# MCP Servers and Approval

## Connecting to an MCP Server

An [MCP](https://modelcontextprotocol.io) server exposes tools over a
standard protocol, instead of a Python function you write yourself. Runa
speaks it over two transports:

```python
from runa import Agent, MCPServer

files = MCPServer(name="files").stdio("npx", ["-y", "@modelcontextprotocol/server-filesystem", "."])
search = MCPServer(name="search").http("https://example.com/mcp")


class Assistant(Agent):
    name = "assistant"
    instructions = "..."
    mcp = [files, search]
```

The server's tools are listed once (and cached) the first time the agent
needs them, then exposed to the model exactly like an ordinary `@tool`
function — the model can't tell the difference. The connection itself
opens lazily and stays open for the agent's whole lifetime, not reopened
every turn.

`mcp=` is sugar for `mcp_servers=`; pass either.

## Human Approval

Some tool calls are sensitive enough that a person should sign off before
they run — deleting a record, sending an email, spending money. Gate a
tool with `needs_approval`:

```python
from runa import Agent, approval, tool


@approval
def confirm_amount(amount: float) -> bool:
    """Only auto-approve refunds under $50."""
    return amount < 50


@tool(needs_approval=confirm_amount)
def issue_refund(amount: float) -> str:
    """Refund the customer."""
    ...
```

`@approval` wraps a predicate the same way `@guardrail` does, but returns
`True` to *allow* the call (the opposite sense of a guardrail's tripwire).
Its parameters are looked up by name from the tool call's arguments; name
one `ctx` or `call_id` to receive the run context or call id instead.

You can also pass `needs_approval=True` to always require approval, with
no predicate.

`runa chat` prompts interactively for any call that needs approval:

```
approve issue_refund({"amount": 120})? [y/N]
```

Rejecting a call skips the tool entirely; the model sees "rejected by the
operator" instead of a result.
