# The Runa CLI

The `runa` command scaffolds a Runa application and operates one already
running. It never contains logic of its own: every subcommand calls an
existing library function against the app in the current directory, so
anything it does you can also do from ordinary Python. See
[Getting Started](getting_started.md) for the commands in context, and
[Runa Guides](guides.md) for background execution and approval workflows
that show up through `runa runs`.

## `runa new <name>`

Scaffolds a new Runa application into `<name>/`, following the conventional
`app/agents/`, `app/tools/`, `app/resources/`, `app/evaluations/`,
`app/tests/` layout described in
[Getting Started §1](getting_started.md#1-create-a-project).

## `runa generate <kind> <Name>`

Generates scaffolding inside an existing Runa application, following the
same convention `runa new` sets up:

* `runa generate agent <Name>`, a new agent module under `app/agents/`
* `runa generate tool <Name>`, a new tool module under `app/tools/`
* `runa generate evaluation <Name>`, a new case module under `app/evaluations/`

## `runa run <Agent> <input>`

Runs an Agent from `app/agents/` against `input` and prints the completed
Run's id, status, and result: `runa run Support "my order hasn't arrived"`.
`<Agent>` matches the class name exactly, or its name with the `Agent`
suffix left off, following `runa generate agent`'s own convention, so
`Support` finds `SupportAgent`.

Equivalent to importing the Agent into `main.py` and calling
`SupportAgent.run(...)` directly; the CLI's version also saves the Run to
`application.run_store` afterward, so `runa runs show <id>` can find it
right away without any extra wiring.

## `runa test`

Runs `app/tests/`: deterministic invariants about your application's
behavior. See [Getting Started §12](getting_started.md#12-evaluate-an-agent).

## `runa eval`

Runs `app/evaluations/`: probabilistic grading of Agent behavior, distinct
from `runa test`. See [Getting Started §12](getting_started.md#12-evaluate-an-agent).

## `runa runs`

Inspects Runs saved to a `RunStore`, which only holds a Run once your
application has actually persisted it (see
[Persistence](concepts.md#persistence) and
[Inspecting Runs](guides.md#inspecting-runs)).

* `runa runs show <run_id>`, print a Run's event timeline
* `runa runs list [--status] [--since] [--agent-name] [--parent-run-id]`, list Runs, optionally filtered
* `runa runs pending`, list Runs paused awaiting approval
* `runa runs approve <run_id> <tool_call_id>`, approve a pending tool call and resume the Run
* `runa runs deny <run_id> <tool_call_id> [--reason]`, deny a pending tool call and fail the Run
* `runa runs cancel <run_id>`, cancel a saved Run that isn't currently being driven

See [Adding Human Approval](guides.md#adding-human-approval) and
[Cancelling a Run](guides.md#cancelling-a-run) for the workflows behind
`approve`/`deny` and `cancel`.
