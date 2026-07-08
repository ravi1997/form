from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.condition_evaluator import ConditionEvaluator
from app.models.form import Condition


def benchmark(iterations: int = 2000):
    condition = Condition(
        uuid="bench-1",
        conditionType="comparison",
        targetField="score",
        operator="between",
        operands=["40", "90"],
        isActive=True,
    )
    evaluator = ConditionEvaluator(
        {"score": 75}, enable_request_cache=True, enable_timing=True
    )

    started = time.perf_counter()
    for _ in range(iterations):
        evaluator.evaluate(condition)
    elapsed = (time.perf_counter() - started) * 1000
    print(
        {
            "iterations": iterations,
            "total_ms": round(elapsed, 2),
            "avg_ms": round(elapsed / iterations, 4),
            "cache": evaluator.get_request_cache_stats().to_dict()
            if evaluator.get_request_cache_stats()
            else {},
        }
    )


if __name__ == "__main__":
    benchmark()
