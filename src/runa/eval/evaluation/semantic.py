"""eval/evaluation/semantic.py: the default semantic metrics, activated by evidence.

Each metric only runs when the `Case`/`AgentRun` actually supplies what it needs to judge:
correctness needs a reference answer, faithfulness needs retrieval context, tool correctness
needs an expected tool. Task completion and answer relevance need neither, so they always run.
"""

from deepeval.metrics import (
    AnswerRelevancyMetric,
    FaithfulnessMetric,
    GEval,
    TaskCompletionMetric,
    ToolCorrectnessMetric,
)
from deepeval.test_case import SingleTurnParams

from runa.eval.case import Case
from runa.eval.evaluation.core import EvaluationResult, Status
from runa.eval.integrations.deepeval import build_test_case, judge_model, run_metric
from runa.eval.tracing.adapter import AgentRun

_CORRECTNESS_CRITERIA = (
    "Determine whether the actual output is substantively correct relative to the expected "
    "output: it may be worded differently, but must not contradict or omit its key claims."
)


async def evaluate_semantic(
    case: Case, run: AgentRun, *, model: str, thresholds: dict[str, float]
) -> list[EvaluationResult]:
    """Run every semantic metric that applies to `case`, recording `SKIPPED` for the rest."""
    test_case = build_test_case(case, run)
    judge = judge_model(model)

    results = [
        await run_metric(
            "task_completion",
            TaskCompletionMetric(model=judge, threshold=thresholds["task_completion"]),
            test_case,
        ),
        await run_metric(
            "answer_relevance",
            AnswerRelevancyMetric(model=judge, threshold=thresholds["answer_relevance"]),
            test_case,
        ),
    ]

    if case.expected is not None:
        correctness_metric = GEval(
            name="Correctness",
            criteria=_CORRECTNESS_CRITERIA,
            evaluation_params=[
                SingleTurnParams.INPUT,
                SingleTurnParams.ACTUAL_OUTPUT,
                SingleTurnParams.EXPECTED_OUTPUT,
            ],
            model=judge,
            threshold=thresholds["answer_correctness"],
        )
        results.append(await run_metric("answer_correctness", correctness_metric, test_case))
    else:
        results.append(
            EvaluationResult(
                metric="answer_correctness", status=Status.SKIPPED, reason="no expected answer"
            )
        )

    if case.context:
        faithfulness_metric = FaithfulnessMetric(model=judge, threshold=thresholds["faithfulness"])
        results.append(await run_metric("faithfulness", faithfulness_metric, test_case))
    else:
        results.append(
            EvaluationResult(
                metric="faithfulness", status=Status.SKIPPED, reason="no retrieval context"
            )
        )

    if case.expected_tool is not None:
        tool_metric = ToolCorrectnessMetric(model=judge, threshold=thresholds["tool_correctness"])
        results.append(await run_metric("tool_correctness", tool_metric, test_case))
    else:
        results.append(
            EvaluationResult(
                metric="tool_correctness", status=Status.SKIPPED, reason="no expected tool"
            )
        )

    return results
