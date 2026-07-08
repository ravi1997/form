# Condition Testing Guide

Key tests:
- DSL: tokenizer/parser/validator/evaluator safety and function coverage.
- Evaluator: temporal/arithmetic/set operators, recursion limits, cycle detection.
- Cache: request/ttl/historical/negative + invalidation + metrics.
- API: metadata/test/batch/presets/approval/versioning/bulk/async endpoints.
- Monitoring: graph/heatmap/unused/most-used/evaluation stats.

Run:
```bash
pytest -v tests/test_condition_*.py tests/test_conditions_api.py
```
