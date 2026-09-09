# Tools and Guardrails

## Tools

A tool is a plain Python function. `@tool` derives its JSON schema from the
function's signature and docstring — there's nothing else to declare.

```python
from runa import tool


@tool
def get_weather(city: str) -> str:
    """Return the current weather for a city."""
    ...
```

* The docstring becomes the tool's description.
* Type hints become the JSON schema (`str`, `int`, `float`, `bool`,
  `list[T]`, `dict`, `Literal[...]`, `Enum` subclasses, and `T | None` are
  all understood; anything else falls back to an unconstrained schema).
* A parameter with no default is required; one with a default is optional.

Attach tools to an agent:

```python
class WeatherAgent(Agent):
    name = "weather_agent"
    instructions = "You answer questions about the weather."
    tools = [get_weather]
```

The model decides on its own when to call a tool — you never invoke it
directly.

### Async Tools

`@tool` works on `async def` functions the same way:

```python
@tool
async def fetch_price(symbol: str) -> float:
    """Look up a stock's current price."""
    ...
```

### Reserved Parameters

Name a parameter `ctx` or `call_id` to receive the run's `RunContextWrapper`
or the tool call's id instead of a model-supplied argument. Neither appears
in the tool's schema:

```python
@tool
def whoami(ctx) -> str:
    """Return the current user's name from run context."""
    return ctx.context.user_name
```

## Guardrails

A guardrail is a predicate: `(value) -> bool`, tripping the run when it
returns `True`.

```python
from runa import guardrail


@guardrail
def block_empty(input: str) -> bool:
    """Trip when the user sends an empty message."""
    return not input.strip()
```

Bind it to a side with `.input` or `.output`, and list it on an agent:

```python
class SupportAgent(Agent):
    name = "support_agent"
    instructions = "..."
    guardrails = [block_empty.input]
```

* On `.input`, the predicate sees the latest user message as plain text.
* On `.output`, it sees the agent's final output.
* `.i`/`.o` are shorthand for `.input`/`.output` — the exact same binding,
  just shorter to type. There's no other way to bind a guardrail.

Listed bare (no `.input`/`.output`), a guardrail is wired to both sides:

```python
guardrails = [block_empty.input, contains_pii]  # contains_pii checks input and output
```

Group them explicitly instead, if you'd rather be specific:

```python
guardrails = {"input": [block_empty], "output": [contains_pii]}
```

A tripped guardrail stops the run before the model call (input side) or
before the caller sees the output (output side); `run`/`run_sync` come
back with `status="error"` instead of raising.

### Guardrails on Tools

The same `@guardrail` predicate works against a tool's arguments or return
value, via `@tool(guardrails=[...])`:

```python
@guardrail
def no_args(args: dict) -> bool:
    """Trip if this tool is somehow called with arguments."""
    return bool(args)


@tool(guardrails=[no_args.input])
def now() -> str:
    """Return the current time."""
    ...
```

On a tool, `.input` sees the call's parsed arguments as a `dict`; `.output`
sees the tool's raw return value. A guardrail that only observes — logs,
metrics — without ever tripping just always returns `False`.

### Async Guardrails

A guardrail predicate can be `async def` too; it's awaited automatically.

## Human Approval

Some tool calls shouldn't run without a person saying yes. That's a
different mechanism from a guardrail — a guardrail's predicate is the
final verdict, `needs_approval`'s predicate only decides whether to stop
and ask a human — see [Human Approval](approval.md).
