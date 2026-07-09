# Changelog

All notable changes to this project are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Changed

- **Deprecation fix**: replaced all `datetime.utcnow()` calls (deprecated since Python 3.12) with `datetime.now(timezone.utc)` across `app/` and `tests/`. The condition evaluator's internal naive-UTC path (`_coerce_datetime`) is preserved intentionally for datetime arithmetic consistency.
- **Rate limiting**: `Retry-After` and corrected `X-RateLimit-Remaining` headers are now included in all 429 responses from the `rate_limit` and `rate_limit_by_endpoint` decorators in `app/middleware/rate_limit.py`.
- **Rate limiting**: Redis-backed counters now reset the window timestamp correctly after expiry in `app/services/rate_limit.py`.
- **Audit logging**: `log_audit` now prefers `uuid` over `id` when capturing resource identifiers from returned payloads and model instances.
- **Condition evaluation**: numeric temporal inputs are treated as Unix timestamps, and DSL string literals now preserve Unicode characters.
- **Async evaluation**: timeout retries are re-queued instead of recursively blocking the worker thread.
- **Async execution**: Celery now executes async condition jobs via Redis-backed workers while MongoDB remains the source of truth for job history, retries, and audit state.
- **Async observability**: `/api/v1/metrics` now reports created, queued, running, retrying, success, failed, timeout, and cancelled async jobs plus Celery worker availability.
- **Deployment**: Docker Compose now includes Redis, a Celery worker, and an optional beat service for async execution.
- **Monitoring retention**: condition evaluation statistics now use a 30-day MongoDB TTL index so the analytics collection stays bounded.
- **Resource coverage**: nested section, question, and choice lifecycle tests now verify invalid version links, missing parent resources, and delete cascades at the API layer.
- **Deployment**: Docker Compose now requires MongoDB authentication and connects the app with `authSource=admin`.
- **Documentation**: architecture, deployment, observability, and technical debt docs now describe the Celery/Redis job model and operational workflow.

### Added

- `ARCHITECTURE.md` — full architecture reference including request flow, auth model, RBAC, form workflow, condition system, and data model.
- `SECURITY.md` — security model, headers, known limitations, and responsible disclosure.
- `DEVELOPMENT.md` — local setup, IDE recommendations, debugging, and conventions.
- `DEPLOYMENT.md` — Docker, production checklist, gunicorn config, Kubernetes probes, JWT key rotation, and CI/CD overview.
- `CONTRIBUTING.md` — branch naming, commit conventions, PR process, code standards.
- `TESTING.md` — test strategy, fixture reference, writing guidelines, coverage approach.
- `CHANGELOG.md` — this file.
- `Makefile` — common developer tasks (`install`, `test`, `lint`, `type-check`, `format`, `audit`, `docker-build`, `docker-up`, `docker-down`, `clean`).

---

## [1.0.0] — Initial release

### Added

- OpenAPI 3 endpoints under `/api/v1` powered by flask-openapi3.
- JWT authentication with access + refresh token pair, session tracking, refresh token rotation, and token blocklisting.
- Admin endpoints for session management and audit log queries.
- Role-based access control (RBAC) with per-organisation role scoping.
- Project → Form → Section → Question → Choice resource hierarchy with full CRUD.
- Version management for Projects, Forms, Sections, and Questions.
- Form workflow state machine: `draft → submitted → in_review → approved / rejected`.
- Condition evaluation engine supporting 8 condition types: `regex`, `comparison`, `logical`, `temporal`, `arithmetic`, `set`, `dsl`, `custom`.
- Condition management: presets, versioning, approval workflow, async evaluation, monitoring, impact analysis.
- Sandboxed arithmetic DSL (`safe_dsl.py`) for condition expressions.
- Condition evaluation caches: TTL cache, historical cache, negative cache.
- Configurable rate limiting: MongoDB bucket counters for auth endpoints; Redis-backed priority-tier rules for general API.
- Admin API for managing rate limit rules (`/api/v1/rate-limits`).
- UI template management (`/api/v1/ui-templates`): layout and theme templates.
- Structured rotating log files: `requests.log`, `responses.log`, `app.log`, `debug.log`, `errors.log`.
- Full request/response audit logging with `X-Request-Id` correlation throughout.
- Security headers: `X-Content-Type-Options`, `X-Frame-Options`, `CSP`, `HSTS`, `Referrer-Policy`, `Permissions-Policy`.
- Configurable CORS via `CORS_ALLOW_ORIGINS`.
- Health (`/health`), liveness (`/liveness`), readiness (`/readiness`), and metrics (`/metrics`) endpoints.
- Legacy URL redirects (308) for `/api/health`, `/api/auth/*`, `/api/projects/*`.
- Docker multi-stage build with non-root user.
- Docker Compose setup with MongoDB 8 and health checks.
- GitHub Actions CI: lint, type check, tests, coverage, pip-audit, Docker build, smoke test.
- `scripts/` directory: `benchmark_conditions.py`, `init_rate_limits.py`, `setup_condition_indexes.py`.
- 337 automated tests with mongomock (no real MongoDB required).
