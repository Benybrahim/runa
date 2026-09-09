# Cache

A minimal, general-purpose cache — independent of [Agent](agents.md),
[Memory](memory.md), and [Sessions](sessions.md). Nothing wires it into
the run lifecycle automatically; use it directly wherever your own code
wants to cache something (an expensive tool call, an external API
response, a computed value):

```python
from runa import MemoryCache

cache = MemoryCache()
await cache.set("weather:paris", {"temp_c": 18}, ttl=300)
await cache.get("weather:paris")  # {"temp_c": 18}, until it expires
```

Every backend implements the same four async methods:

```python
await cache.get(key)  # value, or None if missing/expired
await cache.set(key, value, ttl=60)  # ttl in seconds; None never expires
await cache.delete(key)
await cache.clear()
```

Expiration is lazy — an expired entry is only evicted (and reported as a
miss) the next time `get` looks it up, not by a background sweep.

## `MemoryCache`: in-process

A plain dict, gone when the process exits:

```python
from runa import MemoryCache

cache = MemoryCache()
```

## `SQLiteCache`: persistent

Backed by the `cache_entries` table inside `runa.db` — the same file
`SQLiteSession` and `Memory` use, created automatically on first use:

```python
from runa import SQLiteCache

cache = SQLiteCache()  # db/runa.db by default
cache = SQLiteCache("db/cache.db")  # or your own file
```

Values are serialized with `json.dumps`/`json.loads`, so only
JSON-serializable values (dicts, lists, strings, numbers, booleans,
`None`) can be cached.

## Writing your own backend

`Cache` is a `Protocol` — any object with `get`/`set`/`delete`/`clear`
matching that shape works, no inheritance required. Swap in Redis, a
different SQL database, or anything else your app needs.
