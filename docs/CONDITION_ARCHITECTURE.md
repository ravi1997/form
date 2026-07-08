# Condition System Architecture

## Components
- `Condition` model supports regex/comparison/logical/custom/temporal/arithmetic/set types.
- `ConditionEvaluator` provides safe evaluation, tracing, timing, complexity/depth safeguards.
- `condition_cache` provides request cache, TTL cache, historical cache, bloom-like negative cache, invalidation manager.
- `condition_management` manages presets, version history, approval workflow, analytics, and async jobs.
- `conditions` API blueprint exposes metadata, testing, cache, usage, approval, versioning, bulk, monitoring, async endpoints.

## Safety
- max recursion depth, cycle detection, operand caps, timeout protection.
- DSL parser/tokenizer/validator/evaluator (no `eval`).

## Observability
- trace + execution path + timing snapshot.
- persisted evaluation stats for graph/heatmap/unused/most-used dashboards.
