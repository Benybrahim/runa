"""Shared test fixtures.

Tracing is automatic (see `runa.tracing`), so any test that drives a real `Runner.run()` call,
directly or through `Agent.run`/`run_sync`/`run_agent_for_eval`, produces a real finished trace
that the default `SQLiteExporter` would otherwise persist to `runa.db` in the process's cwd. No
test should touch that real file, so every test runs with trace export disabled by default; a
test that specifically wants to exercise an exporter (e.g. a fail-open test) can still pass its
own `exporter=` to `observe(...)`, which simply overrides this for the scope of its `with` block.
"""

import pytest

from runa.tracing import observe


@pytest.fixture(autouse=True)
def _no_default_trace_export():
    """Disable the default `SQLiteExporter` for the duration of every test."""
    with observe(exporter=[]):
        yield
