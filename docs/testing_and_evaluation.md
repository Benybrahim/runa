# Testing and Evaluating Agents

Runa distinguishes two kinds of checks: **tests** verify invariants with a
plain `assert`; **evals** grade behavior, including with a judge model,
against a dataset of cases.

## Testing

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

## Evaluating

`app/evaluations/` holds datasets of `Case`s, graded against an agent:

```bash
runa generate evaluation SupportAgent
```

```python
# app/evaluations/support_agent_eval.py
from runa import Case

from app.agents.support_agent import SupportAgent

agent = SupportAgent()

dataset = [
    Case(
        input="Where's my order #4821?",
        expected="Asks for or looks up the order status",
    ),
]
```

```bash
runa eval
```

A module must declare module-level `agent` and `dataset`; `runa eval`
imports every module under `app/evaluations/` and calls
`agent.evaluate(dataset)` on each — the same path production evaluation
runs through.

### What a `Case` Can Carry

Only `input` is required. Everything else is optional evidence that
decides which metrics run:

| Field           | Enables                                    |
|-----------------|----------------------------------------------|
| `expected`      | Answer-correctness grading                  |
| `expected_tool` | Deterministic "was it called" tool-correctness check |
| `context`       | Faithfulness grading against retrieval passages |
| `metadata`      | Arbitrary data carried through to the report |

With none of them, task completion and answer relevance still run. Every
case runs to completion even if an earlier one errors, and the finished
`Report` is persisted to `runa.db`.

### Choosing a Judge

Semantic metrics (task completion, answer correctness/relevance,
faithfulness, tool correctness) are graded by a judge model — by default,
the agent's own `model`:

```python
report = await agent.evaluate(dataset, judge="gpt-5.4")
```

Override a pass threshold globally or per metric:

```python
await agent.evaluate(dataset, threshold=0.8)
await agent.evaluate(dataset, thresholds={"faithfulness": 0.9})
```
