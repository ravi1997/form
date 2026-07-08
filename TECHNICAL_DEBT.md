# Technical Debt

This file tracks known deferred work that is not blocking the current remediation pass.

## Production blockers deferred

- `ConditionEvaluationStat` now uses a 30-day MongoDB TTL index; broader archival policy for other analytics collections remains deferred.

## Engineering improvements

- Resources API now has authenticated CRUD and nested lifecycle coverage, but more edge-case validation around relationship errors and deletion cascades would still be useful.
- Async condition jobs are now recovered from MongoDB on startup, but a fully durable external queue is still preferable for higher throughput or multi-worker scale-out.
- `app/middleware/rate_limit.py` remains a compatibility layer with known decorator limitations on `flask-openapi3` routes.
- The repository still has duplicated UTC helper patterns across modules.

## Nice-to-have items

- More complete module and function docstrings.
- More test coverage for rate limit API paths and resources CRUD endpoints.
- Consolidating some legacy schema aliases and duplicated model fields.
- Evaluate whether the condition evaluation stats TTL window should be configurable per deployment once operational usage is known.
