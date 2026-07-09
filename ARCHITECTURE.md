# Architecture

## Overview

Form Service is a production-ready REST API built with **Flask** and **flask-openapi3**, backed by **MongoDB** via **MongoEngine** and **Celery/Redis** for durable async execution. It manages hierarchical form structures (Projects → Forms → Sections → Questions → Choices), user authentication with JWT session management, condition evaluation, rate limiting, job lifecycle tracking, and audit logging.

```
┌─────────────────────────────────────────────────────────────┐
│                         Clients                             │
└──────────────────────┬──────────────────────────────────────┘
                       │ HTTP
┌──────────────────────▼──────────────────────────────────────┐
│                  Gunicorn / WSGI (app.wsgi)                  │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│              Flask OpenAPI3 Application                      │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                   Middleware Layer                    │   │
│  │  • RequestID (request_id.py)                         │   │
│  │  • Observability / CORS / Security Headers           │   │
│  │  • Rotating Request/Response Logger                  │   │
│  └─────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                    API Layer                          │   │
│  │  • /api/v1/health  (health, liveness, readiness)     │   │
│  │  • /api/v1/auth    (register, login, refresh, logout) │   │
│  │  • /api/v1/projects, /forms, /sections, /questions   │   │
│  │  • /api/v1/conditions                                 │   │
│  │  • /api/v1/rate-limits                                │   │
│  │  • /api/v1/ui-templates                               │   │
│  └─────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                  Service Layer                        │   │
│  │  • AuthService (JWT + session lifecycle)              │   │
│  │  • RBAC (role-based access control)                   │   │
│  │  • ConditionEvaluator (DSL + type system)             │   │
│  │  • RateLimitService (Redis / in-memory fallback)      │   │
│  │  • Celery task layer (Redis broker, MongoDB ledger)   │   │
│  │  • RotatingLoggerService (structured file logging)    │   │
│  └─────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                   Data Layer                          │   │
│  │  • MongoEngine documents (form, user, auth)           │   │
│  │  • Pydantic v2 schemas (validation + serialisation)   │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────┬───────────────────────────────────┘
                          │
            ┌─────────────▼──────────────┐
            │   MongoDB (mongoengine)     │
            └────────────────────────────┘

                       ▲
                       │ lifecycle/audit state
                       │
┌──────────────────────▼──────────────────────────────────────┐
│                      Celery / Redis                         │
│   Flask API → Celery client → Redis broker → workers        │
│   MongoDB stores job metadata, retry history, and audit     │
└─────────────────────────────────────────────────────────────┘
```

---

## Directory Structure

```
app/
├── __init__.py               # exports create_openapi_app
├── wsgi.py                   # WSGI entry point
├── openapi.py                # Application factory
├── config.py                 # Configuration classes and env loading
├── extensions.py             # MongoEngine Flask integration
│
├── api/                      # Route handlers (thin controllers)
│   ├── __init__.py           # Blueprint registration + legacy redirects
│   ├── auth.py               # Authentication endpoints
│   ├── auth_support.py       # Auth blueprint, helpers, hooks
│   ├── auth_admin_routes.py  # Admin session/audit endpoints
│   ├── health.py             # Health, liveness, readiness, metrics
│   ├── conditions.py         # Condition test/manage endpoints
│   ├── rate_limit.py         # Rate limit config CRUD
│   ├── ui_templates.py       # UI template endpoints
│   ├── resources.py          # Resource API facade (imports sub-modules)
│   ├── resources_support.py  # Resources blueprint, auth hook, rate limit gate
│   ├── resources_utils.py    # RBAC helpers, pagination, security events
│   ├── resources_context.py  # Shared context resolvers and update helpers
│   ├── resources_schemas.py  # Path/query/response schema models
│   ├── resources_projects.py # Project CRUD + version endpoints
│   ├── resources_forms.py    # Form CRUD + workflow + UI config
│   ├── resources_sections.py # Section CRUD + versions
│   ├── resources_questions.py# Question CRUD + versions
│   ├── resources_choices.py  # Choice CRUD
│   └── resources_actions.py  # Action trigger + execution list
│
├── middleware/               # Flask before/after_request hooks
│   ├── request_id.py         # Assign/propagate X-Request-Id
│   ├── observability.py      # Metrics collection + security headers + CORS
│   └── rotating_logger_middleware.py  # Full request/response audit logging
│
├── models/                   # MongoEngine documents
│   ├── user.py               # User, Organization
│   ├── auth.py               # UserSession, TokenBlocklist, RateLimitCounter, SessionAuditLog
│   ├── form.py               # Project, Form, Section, Question, Choice, Condition, FormResponse, Version
│   ├── condition_management.py # ConditionPreset, ConditionVersion, ConditionApprovalAudit, etc.
│   ├── rate_limit.py         # RateLimitConfig, RateLimitLog
│   └── ui_template.py        # LayoutTemplate, ThemeTemplate
│
├── schemas/                  # Pydantic v2 request/response models
│   ├── common.py             # SchemaModel base
│   ├── auth.py               # Auth request/response schemas
│   ├── user.py               # UserOutput schema
│   ├── form.py               # Form create/update/output schemas
│   ├── project.py            # Project schemas
│   ├── section.py            # Section schemas
│   ├── question.py           # Question schemas
│   ├── choice.py             # Choice schemas
│   ├── action.py             # Action schemas
│   ├── condition.py          # Condition schemas
│   ├── condition_management.py # Condition management operation schemas
│   ├── mappers.py            # Model → schema conversion helpers
│   └── ...
│
└── services/                 # Business logic
    ├── auth.py               # JWT creation, decoding, session management
    ├── rbac.py               # Role-based access control checks
    ├── security.py           # Rate limit counter (MongoDB), audit log writer
    ├── rate_limit.py         # RateLimitService (Redis + in-memory fallback)
    ├── condition_evaluator.py # Full condition evaluation engine
    ├── condition_dsl.py      # DSL parser for complex conditions
    ├── safe_dsl.py           # Sandboxed arithmetic expression evaluator
    ├── condition_cache.py    # TTL/historical/negative caches for conditions
    ├── condition_management.py     # Condition lifecycle orchestrator
    ├── condition_management_core.py
    ├── condition_management_approval.py
    ├── condition_management_versioning.py
    ├── condition_management_presets.py
    ├── condition_management_analysis.py
    ├── condition_management_async.py
    ├── celery/                # Celery app, tasks, signals, config
    ├── condition_management_graph.py
    ├── condition_management_monitoring.py
    ├── rotating_logger.py    # RotatingLoggerService (singleton)
    ├── logger.py             # Backward-compat facade
    └── logging/              # Structured logging primitives
        ├── service.py
        ├── formatter.py
        └── decorators.py

Operational notes:
- Async condition jobs are executed by Celery workers with Redis as the broker and result backend.
- MongoDB remains the source of truth for job metadata, retry history, execution timestamps, and audit state.
- Flask tasks run inside the active Flask application context via a custom Celery task base.
- Celery worker startup is independent from API startup and is exposed via `app.celery.worker`.
- Queue status is observable via `GET /api/v1/metrics`, the async job status endpoint, and Celery worker logs/inspect output.
- Condition evaluation statistics use a MongoDB TTL index on `created_at` with a 30-day retention window, preventing unbounded growth of the analytics collection.
```

---

## Request / Response Flow

```
1. Request arrives at Gunicorn
2. Flask dispatcher selects route
3. before_request hooks (in order):
   a. assign_request_id       — generate/propagate X-Request-Id → g.request_id
   b. _before_request_metrics — start perf timer, increment inflight counter
   c. before_request_logging  — log request details (method, path, headers, body)
   d. _before_resources_request (resources API only):
      - resources_rate_limit() — check rate limit via RateLimitService
      - resolve_access_identity_from_header() — decode JWT access token
      - authorize_resources_route() — RBAC permission check
4. Route handler executes (thin controller, delegates to services)
5. after_request hooks (in order):
   a. after_request_logging   — log response (status, body, duration)
   b. _after_request_metrics_and_headers — record metrics, set security headers,
                                           CORS headers
   c. inject_request_id_header — echo X-Request-Id in response
6. Response sent to client

Startup recovery:
- `create_openapi_app()` initializes Celery after the Flask app and MongoDB connection are ready.
- Jobs that were queued or running when a worker exited remain durable in MongoDB and can be resumed by Celery workers after restart.
- `GET /api/v1/metrics` includes a snapshot of created, queued, running, retrying, success, failed, timeout, and cancelled async jobs.
- `condition_evaluation_stats` is automatically aged out by MongoDB after 30 days via a TTL index on `created_at`.

## Future Roadmap

The detailed deferred roadmap lives in [FUTURE_IMPROVEMENTS.md](FUTURE_IMPROVEMENTS.md).
It documents the next major design decisions for:

- schema version migration
- event-driven actions and webhooks
- multi-tenant sharing
- pessimistic form locks
- proof-of-work protection for public submissions
```

---

## Authentication Flow

```
Register/Login → TokenPairResponse { access_token, refresh_token, session_uuid }
               → Creates UserSession record in MongoDB
               → Access token TTL: 30 min (configurable)
               → Refresh token TTL: 7 days (configurable)

API calls      → Authorization: Bearer <access_token>
               → decode_token() validates JWT signature + type + claims
               → get_user_by_uuid() verifies user still exists
               → touch_session() updates last_seen_at

Refresh        → POST /auth/refresh { refresh_token }
               → rotate_refresh_token():
                 - Validates refresh token is not revoked/session-mismatched
                 - Blocklists old refresh token
                 - Issues new refresh + access token pair
                 - Updates UserSession with new JTI + hash

Logout         → POST /auth/logout { refresh_token }
               → revoke_refresh_token() → blocks JTI + deactivates UserSession

Token security → TokenBlocklist: MongoDB TTL collection expiring at token exp time
               → refresh_token_hash (SHA-256): prevents token substitution attacks
               → Multiple JWT keys supported via JWT_ADDITIONAL_KEYS (key rotation)
```

---

## Role-Based Access Control (RBAC)

```
User roles are stored per-organization: roles = { "org_uuid": ["admin", "editor", ...] }

Role hierarchy:
  super_admin      → all operations globally
  org admin        → all operations within their organizations
  admin            → project admin (full CRUD, delete, workflow approve)
  editor           → project write (create, update forms/sections/questions)
  reviewer         → project review (can submit workflow to in_review state)
  approver         → project approve (can transition to approved)
  submitter        → project submit (can transition to submitted)
  viewer           → project read (read-only access)
  authenticated    → any authenticated user

Permission lookup: ENDPOINT_PERMISSION map in resources_utils.py
```

---

## Form Workflow

```
States: draft → submitted → in_review → approved
                                      → rejected → submitted (re-submit)

Transitions:
  draft    → submitted   (submitter role)
  submitted → in_review  (reviewer role)
  in_review → approved   (approver role, requires strict_review_before_approve if enabled)
  in_review → rejected   (approver/reviewer role)
  rejected  → submitted  (submitter role)

WorkflowEvent records every transition with actor, timestamp, note.
WORKFLOW_STRICT_REVIEW_BEFORE_APPROVE: if true, approved requires prior in_review.
```

---

## Condition Evaluation System

The condition evaluator supports 8 condition types:

| Type         | Description                                      |
|-------------|--------------------------------------------------|
| `regex`      | Field matches a regular expression              |
| `comparison` | Numeric/string comparison (eq, gt, lt, ...)     |
| `logical`    | Combine conditions with AND/OR/NOT              |
| `temporal`   | Time-based checks (created_within_days, etc.)   |
| `arithmetic` | Arithmetic expression over context fields       |
| `set`        | Set operations (subset, superset, intersects)   |
| `dsl`        | Complex custom DSL expressions                  |
| `custom`     | Python-callable conditions (sandboxed)          |

Evaluation caches: TTL cache, historical cache, negative cache (via `condition_cache.py`).

---

## Rate Limiting Architecture

Two independent rate limiting systems coexist:

1. **Auth endpoint rate limiting** (`services/security.py` + `models/auth.py`):
   - Uses MongoDB `RateLimitCounter` with atomic upsert increment
   - Buckets by `(scope, key, bucket_epoch)`
   - TTL index expires old counters automatically

2. **General API rate limiting** (`services/rate_limit.py`):
   - Priority-based: user > organization > route > global
   - Configurable via `RateLimitConfig` MongoDB documents
   - Backend: Redis (primary) → in-memory dict (fallback)
   - Admin API at `/api/v1/rate-limits` to manage rules

---

## Observability

| Endpoint             | Description                                    |
|---------------------|------------------------------------------------|
| `GET /api/v1/health`    | Simple liveness check                       |
| `GET /api/v1/liveness`  | Process-level liveness                      |
| `GET /api/v1/readiness` | MongoDB ping — returns 503 if degraded      |
| `GET /api/v1/metrics`   | In-memory request counters and durations    |

Log files (rotating, in `LOG_DIR`):

| File           | Content                          |
|---------------|----------------------------------|
| `requests.log` | Full request details (masked)   |
| `responses.log`| Full response details            |
| `app.log`      | Application events               |
| `debug.log`    | Debug-level messages             |
| `errors.log`   | Errors with stack traces         |

All log entries include `request_id` / `correlation_id` for tracing.

---

## Data Models (MongoDB Collections)

| Collection               | Purpose                                             |
|-------------------------|-----------------------------------------------------|
| `users`                  | User accounts + roles                              |
| `organizations`          | Organization records                               |
| `user_sessions`          | Active JWT sessions                                |
| `token_blocklist`        | Revoked refresh tokens (TTL expiry)                |
| `session_audit_logs`     | Auth event audit trail (TTL expiry)                |
| `rate_limit_counters`    | Auth rate limit buckets (TTL expiry)               |
| `projects`               | Project containers                                 |
| `forms`                  | Form definitions with versioning                   |
| `sections`               | Form section definitions                           |
| `questions`              | Question definitions with choices                  |
| `form_responses`         | User-submitted form data                           |
| `conditions`             | Condition rule definitions                         |
| `condition_presets`      | Named condition presets for reuse                  |
| `condition_versions`     | Condition version history                          |
| `condition_approval_audit` | Approval workflow audit trail                    |
| `condition_async_jobs`   | Background evaluation job queue                    |
| `condition_evaluation_stats` | Evaluation performance statistics             |
| `rate_limit_configs`     | Configurable rate limit rules                      |
| `rate_limit_logs`        | Rate limit event log                               |
| `layout_templates`       | UI layout template definitions                     |
| `theme_templates`        | UI theme template definitions                      |

---

## Architectural Decisions

- **flask-openapi3** chosen over Flask-RESTful for OpenAPI 3 schema generation and Pydantic validation.
- **MongoEngine** over PyMongo directly for document abstraction and queryset API.
- **JWT key rotation** supported via `JWT_ADDITIONAL_KEYS` for zero-downtime secret rotation.
- **Rotating file logs** instead of stdout-only to support audit requirements; all log files include structured JSON.
- **Condition evaluator** is sandboxed — arithmetic DSL uses `safe_dsl.py` to prevent code injection.
- **Legacy redirects** (308 permanent) provided for `/api/health`, `/api/auth/*`, `/api/projects/*` paths.
