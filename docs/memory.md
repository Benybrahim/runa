# Memory

Long-term, semantic memory — facts that persist *across* conversations,
not just within one (that's a [Session](sessions.md)). Opt an agent in
with `memory`:

```python
class SupportAgent(Agent):
    name = "support_agent"
    memory = "auto"
```

## `"auto"`: the framework remembers for you

Before each run, `Runner` searches memory for anything relevant to the
user's message and adds it to context. After the run, it asks the model
what's durably worth keeping and stores it. No manual `remember`/`search`
calls.

```python
support = SupportAgent()  # memory = "auto"
support.run_sync("I only speak Japanese.")

# ...later, a new run:
support.run_sync("What's my order status?")  # sees "user speaks Japanese"
```

## `"llm"`: the model decides when to look

The model gets a `search_memory` tool and calls it itself. Nothing is
written automatically — call `memory.remember(...)` from your own tools
if you want the model's actions to persist.

```python
class SupportAgent(Agent):
    name = "support_agent"
    memory = "llm"
```

## `Memory` directly

Reach for a `Memory()` instance when you need a non-default
`db_path`/`model`/`store`, or want to call `remember`/`search`/`forget`
yourself, outside the run lifecycle:

```python
from runa import Memory

memory = Memory()
await memory.remember("User prefers email over phone.", user_id="user-42")
matches = await memory.search("how should I contact this user?", user_id="user-42")
await memory.forget(matches[0].id, user_id="user-42")
```

`Memory()` means `db/runa.db` (the same file `SQLiteSession` uses),
`sqlite-vec`, and OpenAI's `text-embedding-3-small` — nothing to
configure for the common case. Every memory is scoped by `user_id`, so
one user's facts never surface in another's search.

Remembering a near-duplicate of an existing memory skips the write and
returns the existing id instead — restating the same fact across
conversations doesn't pile up duplicates.

For a plain get/set/delete/clear cache — no embeddings, no `user_id`
scoping — see [Cache](cache.md) instead.
