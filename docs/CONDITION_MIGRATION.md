# Condition Migration and Index Notes

MongoEngine is used without an external migration framework.

## New collections
- `condition_presets`
- `condition_versions`
- `condition_approval_audit`
- `condition_async_jobs`
- `condition_evaluation_stats`

## Index updates
- `conditions`: `updated_at`, `approval_state`, and compound `(conditionType, operator, targetField)`

Run script:
```bash
python scripts/setup_condition_indexes.py
```
