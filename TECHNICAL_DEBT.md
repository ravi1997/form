# Technical Debt

This file tracks known deferred work that is not blocking the current remediation pass.

## Production blockers deferred

- `ConditionEvaluationStat` growth and other analytics collections should be revisited for TTL or archival policy.

## Engineering improvements

- Resources API now has an authenticated project/form CRUD smoke test, but sections/questions/choices still deserve deeper lifecycle coverage.
- Async condition jobs are now recovered from MongoDB on startup, but a fully durable external queue is still preferable for higher throughput or multi-worker scale-out.
- `app/middleware/rate_limit.py` remains a compatibility layer with known decorator limitations on `flask-openapi3` routes.
- The repository still has duplicated UTC helper patterns across modules.

## Nice-to-have items

- More complete module and function docstrings.
- More test coverage for rate limit API paths and resources CRUD endpoints.
- Consolidating some legacy schema aliases and duplicated model fields.
