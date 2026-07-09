# Technical Debt

This file tracks known deferred work that is not blocking the current remediation pass.

## Production blockers deferred

- `ConditionEvaluationStat` retention is configurable via `MONITORING_STATS_RETENTION_DAYS` and defaults to 30 days; broader archival policy for other analytics collections remains deferred.
- The Celery job ledger is durable, but we still do not have a formal archival/retention policy for completed async job history.

## Engineering improvements

- Resources API now has authenticated CRUD and nested lifecycle coverage, but more edge-case validation around relationship errors and deletion cascades would still be useful.
- Celery now handles async execution, but a future job dashboard or admin API would make operational triage easier.
- `app/middleware/rate_limit.py` remains a compatibility layer with known decorator limitations on `flask-openapi3` routes.
- The repository still has duplicated UTC helper patterns across modules.

## Nice-to-have items

- More complete module and function docstrings.
- More test coverage for rate limit API paths and resources CRUD endpoints.
- Consolidating some legacy schema aliases and duplicated model fields.
- Evaluate whether the condition evaluation stats TTL window should be configurable per deployment once operational usage is known.
- Add a small Celery admin endpoint for worker health if worker fleet visibility becomes operationally important.
