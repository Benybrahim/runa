# Tracing and Hooks

## Tracing

Every `run`/`run_sync`/`run_streamed` call is traced automatically — there's
no separate setup step. A `Trace` is a hierarchical tree of `Span`s: agent,
LLM call, tool call, handoff, guardrail.

```python
run = agent.run_sync("...")
print(run.trace)  # human-readable span tree
```

Traces are persisted to `runa.db` by default. Inspect them from the CLI:

```bash
runa traces list             # most recent traces
runa traces errors           # most recent traces that errored
runa traces show TRACE_ID    # one trace's full span tree
```

### Privacy Policy

`observe()` configures what tracing captures, globally or for a block:

```python
from runa import observe

observe(capture_inputs=False)  # applies immediately, stays applied

with observe(redact=["password", "ssn"]):
    agent.run_sync(...)  # redacted within this block only
```

Options: `capture_inputs`/`capture_outputs` (whether to keep them at all),
`redact` (a list of dict keys to scrub) or a custom `redactor` callable,
and `max_input_bytes`/`max_output_bytes`/`max_tool_result_bytes` to
truncate what's kept.

### Custom Exporters

By default, traces go to `runa.db` via `SQLiteExporter`. Swap or add
exporters:

```python
from runa import ConsoleExporter, SQLiteExporter, observe

observe(exporter=[SQLiteExporter(), ConsoleExporter()])
```

Write your own by implementing `TraceExporter`'s single method,
`export(self, trace: Trace) -> None`.

## Hooks

Tracing is unconditional; hooks are optional lifecycle callbacks for your
own logic — logging, metrics, side effects.

`RunHooks` is passed per-call and fires for every agent involved in a run
(including subagents):

```python
from runa import RunHooks

class MyHooks(RunHooks):
    async def on_tool_end(self, context, agent, tool, result):
        print(f"{tool.name} -> {result!r}")

agent.run_sync("...", hooks=MyHooks())
```

`AgentHooks` is scoped to a single `Agent` subclass instead, via its
`hooks` class attribute — it fires only for that agent, not for the whole
run:

```python
class SupportAgent(Agent):
    name = "support_agent"
    hooks = MyAgentHooks()
```

Both fire `on_agent_start`, `on_agent_end`, `on_handoff`, `on_tool_start`,
`on_tool_end`, `on_llm_start`, `on_llm_end` — every method is a no-op
unless overridden. `LoggingRunHooks`/`LoggingAgentHooks` (the defaults) log
each event through the standard `logging` module, under the `"runa"`
logger name.
