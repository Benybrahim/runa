# Subagents

An agent can bring in another agent to help, in one of two ways: **handoff**
(transfer control entirely) or **delegate** (call it and get an answer
back). Both are declared with `subagents`.

```python
from runa import Agent


class Researcher(Agent):
    name = "researcher"
    instructions = "You research topics thoroughly and report back findings."


class Translator(Agent):
    name = "translator"
    instructions = "You translate text into French."


class Assistant(Agent):
    name = "assistant"
    instructions = "You help the user, bringing in specialists as needed."
    subagents = [Researcher.handoff, Translator.delegate]
```

## Handoff

`SomeAgent.handoff` transfers the whole conversation to `SomeAgent` — from
that point on, it's the one talking to the user. Use this when a subagent
should fully take over (e.g. "route this support ticket to billing").

## Delegate

`SomeAgent.delegate` wires `SomeAgent` in as a callable tool instead. The
calling agent stays in control: it calls the subagent, gets its output
back, and decides what to do next. Use this when you want a subroutine,
not a handoff (e.g. "ask the researcher, then summarize their answer
yourself").

A bare entry in `subagents` (no `.handoff`/`.delegate`) is wired as
**both** — a handoff and a delegate tool at once — so the model can either
call it for a quick answer or transfer the whole conversation to it:

```python
subagents = [Researcher, Translator.delegate]  # Researcher: both, Translator: delegate only
```

## Naming a Delegate's Tool

A delegated agent is exposed as a tool named after it by default. Override
the name or description it's given:

```python
subagents = [Researcher.delegate(tool_name="research", tool_description="Research a topic.")]
```

## Grouping by Mode

For a longer list, group entries under `"handoff"`/`"delegate"`/`"auto"`
instead of repeating `.handoff`/`.delegate` on each:

```python
subagents = {
    "handoff": [Billing, Returns],
    "delegate": [Researcher, Translator],
}
```

Entries under `"auto"` pass through as given — bare (wired as both) or
already `.handoff`/`.delegate`-bound — for mixing modes within one dict
without forcing every entry the same way.
