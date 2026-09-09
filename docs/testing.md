# Testing Agents

Runa distinguishes two kinds of checks: **tests** verify invariants with a
plain `assert`; **evals** grade behavior, including with a judge model,
against a dataset of cases — see [Evaluation](evaluation.md).

```bash
runa generate tool ...   # nothing special needed — tests are plain functions
```

Any `test_*` function in `tests/` is a test. `runa test` imports every
module under `tests/` and runs them:

```python
# tests/test_support_agent.py
from app.agents.support_agent import SupportAgent


def test_answers_politely():
    run = SupportAgent().run_sync("Hi")
    assert run.status == "completed"
    assert run.output


async def test_handles_async():
    run = await SupportAgent().run("Hi")
    assert run.status == "completed"
```

```bash
runa test
```

An `async def test_*` is awaited automatically. `runa test` isn't a pytest
wrapper — it's a small built-in runner, so a generated app needs no test
framework as a dependency. Use plain `assert`.
