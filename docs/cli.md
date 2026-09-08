# CLI Reference

Every subcommand runs from inside a Runa app (created with `runa new`),
except `runa new` itself.

## `runa new NAME`

Scaffold a new application at `./NAME`, with the conventional layout — see
[Getting Started](getting_started.md).

## `runa generate KIND NAME`

Generate scaffolding inside an existing app:

```bash
runa generate agent MyAgent        # app/agents/my_agent.py
runa generate tool MyTool          # app/tools/my_tool.py
runa generate prompt MyAgent       # app/prompts/my_agent.md
runa generate evaluation MyAgent   # app/evaluations/my_agent_eval.py
```

`agent`'s `NAME` becomes the Python class name (suffixed with `Agent` if
it isn't already); the class's `name` attribute is that class name's
snake_case form, matching the generated filename.

## `runa chat [AGENT_NAME]`

Chat with an agent, or inspect past sessions — see
[Sessions and Chat](sessions.md).

```bash
runa chat support_agent                       # start (or resume) a chat
runa chat support_agent --continue            # resume the most recent session
runa chat support_agent --resume [SESSION_ID] # resume a chosen/given session
runa chat support_agent --session SESSION_ID  # pin an exact session id
runa chat --list                              # list every session
runa chat --show SESSION_ID                   # replay one session's history
```

## `runa test`

Run every `test_*` function under `tests/` — see
[Testing and Evaluating Agents](testing_and_evaluation.md).

## `runa eval`

Run every dataset under `app/evaluations/` against its agent — see
[Testing and Evaluating Agents](testing_and_evaluation.md).

## `runa traces SUBCOMMAND`

Inspect this app's traces in `runa.db` — see [Tracing](tracing.md).

```bash
runa traces list           # most recent traces
runa traces errors         # most recent traces that errored
runa traces show TRACE_ID  # one trace's full span tree
```

## Exit Codes

`runa eval` and `runa test` exit `1` if any case/test failed, `0`
otherwise — safe to wire into CI. Everything else exits `1` only on an
operator error (a mistyped id, running outside a Runa app), printing a
clean message instead of a traceback.
