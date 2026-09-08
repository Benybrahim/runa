# Sessions and Chat

## In-Memory History

By default, an `Agent` instance remembers its own conversation:

```python
agent = SupportAgent()
agent.run_sync("My order hasn't arrived.")
agent.run_sync("It's order #4821.")  # remembers the first message
```

`agent.history` holds this; it only lives as long as the instance does.

## Persisting with `SQLiteSession`

Pass a `session` to persist history to `runa.db` instead, keyed by a
`session_id` you choose:

```python
from runa import SQLiteSession

session = SQLiteSession("user-42")

agent.run_sync("My order hasn't arrived.", session=session)
agent.run_sync("It's order #4821.", session=session)
```

With a `session`, prior turns are read back from `runa.db` automatically —
you only ever pass the new message, and `agent.history` is left untouched.
Reuse the same `session_id` (e.g. a user id, a ticket id) to resume a
conversation from anywhere, including a later process.

`SQLiteSession` also supports:

```python
await session.get_items()      # this session's items, oldest first
await session.pop_item()       # remove and return the most recent item
await session.clear_session()  # delete the session and all its items
```

## `runa chat`

`runa chat` is an interactive REPL that talks to any agent under
`app/agents/`, by its declared `name`:

```bash
runa chat support_agent
```

Every chat starts a fresh session by default, so repeated runs don't pile
onto the same conversation. Pick one back up with:

```bash
runa chat support_agent --continue         # most recent session
runa chat support_agent --resume           # choose from past sessions
runa chat support_agent --resume SESSION_ID  # resume a specific one
runa chat support_agent --session SESSION_ID # pin an exact id
```

Inspect what's stored in `runa.db` without starting a chat:

```bash
runa chat --list              # every session
runa chat --show SESSION_ID   # replay one session's full history
```
