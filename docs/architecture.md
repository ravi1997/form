# Architecture

## Request flow

1. Requests enter the application through `app/wsgi.py`.
2. `app/openapi.py:create_openapi_app()` loads config, runtime settings, request ID middleware, observability, rotating logs, Celery, and route blueprints.
3. `app/api/__init__.py` registers health, auth, resources, conditions, UI template, and rate-limit blueprints.
4. Route handlers perform validation and request shaping, then delegate to `app/services/`.
5. MongoEngine documents in `app/models/` persist the system of record.
6. Celery workers consume async jobs via Redis and operate inside the Flask app context.
7. Celery beat runs periodic maintenance tasks such as password-expiry enforcement.

## Layering

### HTTP layer

- `app/api/` contains the public request handlers
- `flask-openapi3` provides request body validation, response models, and OpenAPI schema generation
- Legacy `/api/...` compatibility redirects are handled in `app/api/__init__.py`

### Middleware layer

- `app/middleware/request_id.py` propagates a request correlation header
- `app/middleware/observability.py` records request metrics and adds security headers
- `app/middleware/rotating_logger_middleware.py` writes structured request and response logs
- `app/middleware/rate_limit.py` enforces generic Redis-backed rate limiting where used

### Service layer

- `app/services/auth.py` owns JWT creation, decoding, token rotation, revocation, and session handling
- `app/services/rbac.py` performs identity and permission checks
- `app/services/password_policy.py` enforces password-age policy and sets `must_change_password`
- `app/services/security.py` handles auth rate-limit counters and session audit logs
- `app/services/rate_limit.py` resolves and applies general rate-limit rules
- `app/services/condition_evaluator.py` evaluates condition trees and DSL expressions
- `app/services/condition_management.py` orchestrates presets, versions, approvals, async execution, and monitoring
- `app/services/logging/` implements structured logging helpers

### Data layer

- `app/models/auth.py` stores sessions, auth counters, audit logs, and refresh-token blocklist entries
- `app/models/user.py` stores users and organizations
- `app/models/form.py` stores projects, forms, sections, questions, choices, actions, conditions, responses, and versions
- `app/models/condition_management.py` stores condition presets, versions, approval audits, async jobs, and evaluation stats
- `app/models/rate_limit.py` stores rate-limit rules and logs
- `app/models/ui_template.py` stores theme and layout templates and revisions

## Key behaviors

### Authentication and sessions

- Access tokens are short-lived JWTs with `type=access`
- Refresh tokens are longer-lived JWTs with `type=refresh`
- Sessions are persisted in `user_sessions`
- Refresh token revocation writes to `token_blocklist` and deactivates the session
- `touch_session()` updates `last_seen_at` for active sessions

### Authorization

- Resource endpoints require a valid access token and an RBAC pass
- Auth admin routes require global or organization admin privileges depending on the endpoint
- `RESOURCE_RBAC_REQUIRE_ORG_ROLE_ALIGNMENT` controls whether project membership must align with org roles

### Rate limiting

- Auth endpoints use MongoDB-backed counters in `rate_limit_counters`
- Resource endpoints use the `RateLimitService`, which prefers Redis and can fall back to in-memory counters
- `RATE_LIMIT_FAIL_OPEN` controls whether Redis unavailability returns a 503 response or raises an error

### Condition work

- Condition testing is synchronous in the API
- Async evaluation is queued through Celery and tracked in `condition_async_jobs`
- Monitoring snapshots and evaluation stats are stored in MongoDB, with TTL retention for the stats collection

### UI templates

- Theme and layout templates are separate document collections
- Templates contain revisions
- A revision must be published before a template can be marked published
- Publishing requires either super-admin or template-admin access

## Startup responsibilities

- `create_openapi_app()` initializes MongoEngine, Celery, request metrics, and logging
- It attempts to ensure the monitoring stats TTL index exists
- `app.celery.app` is configured from the Flask config or environment defaults
- `app.celery.tasks.enforce_password_expiry_task` is scheduled by beat to refresh password-expiry state

## Operational data paths

- Requests and responses are logged as structured events
- Security events are emitted separately from request logs
- Audit logs and session logs are TTL-retained
- Celery job records store status, retries, result state, timing, and lock metadata
