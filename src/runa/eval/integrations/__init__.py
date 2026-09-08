"""`runa.eval.integrations`: third-party evaluation backends, behind `eval/evaluation/semantic.py`.

Nothing outside this package imports DeepEval directly: `evaluation/semantic.py` depends only on
`build_test_case`/`run_metric`/`judge_model`, so the backend could be replaced without touching
the public `agent.evaluate()` API.
"""

from runa.eval.integrations.deepeval import build_test_case, judge_model, run_metric

__all__ = ["build_test_case", "judge_model", "run_metric"]
