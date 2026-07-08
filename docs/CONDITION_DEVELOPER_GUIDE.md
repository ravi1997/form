# Condition Developer Guide

- Use `ConditionEvaluator` for all evaluations; do not use dynamic `eval`.
- Record changes with `record_condition_version` when mutating conditions.
- Use `transition_approval_state` for workflow rules.
- Use `create_or_update_preset` and `sync_auto_update_presets` for templates.
- Use async queue abstraction via `enqueue_async_evaluation`.
- Persist metrics with `record_evaluation_stat`.
