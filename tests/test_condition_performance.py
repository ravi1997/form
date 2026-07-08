import time

import pytest

from app.models.form import Condition
from app.services.condition_evaluator import ConditionEvaluator


@pytest.mark.performance
def test_condition_evaluation_benchmark_runs_fast_enough():
    condition = Condition(
        uuid="perf-1",
        conditionType="comparison",
        targetField="score",
        operator="between",
        operands=["10", "100"],
        isActive=True,
    )
    evaluator = ConditionEvaluator({"score": 45}, enable_request_cache=True)

    started = time.perf_counter()
    for _ in range(1000):
        assert evaluator.evaluate(condition) is True
    elapsed_ms = (time.perf_counter() - started) * 1000

    assert elapsed_ms < 1500
    stats = evaluator.get_request_cache_stats()
    assert stats is not None
    assert stats.hits > 0
