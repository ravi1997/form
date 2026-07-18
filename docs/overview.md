# Overview

Form Service API is a Flask/OpenAPI backend for form management, JWT session auth, condition evaluation, rate limiting, and asynchronous operational workflows. The repository is organized around a small HTTP layer, a larger service layer, and MongoDB-backed documents for all durable state.

## What the service provides

- OpenAPI-backed routes under `/api/v1`
- JWT access and refresh tokens with session tracking
- Password-change enforcement for flagged users and password-expiry policy automation
- RBAC-enforced resource APIs for projects, forms, sections, questions, choices, and actions
- Condition testing, versioning, presets, approval transitions, and async evaluation
- UI template storage for layout/theme configuration and revision publishing
- Enterprise capabilities including form/logic simulation, cryptographic signed audit logs, offline sync keys, collaboration locks, retention governance, webhook policies, and platform analytics
- Health, readiness, metrics, and schema echo routes for operators
- Structured request/response logs, request IDs, and security event logging

## Main functional areas

### Authentication

`app/api/auth.py` and `app/api/auth_admin_routes.py` implement:

- registration
- login
- change-password
- refresh
- logout
- current-user lookup
- session listing
- session revoke
- logout-all
- admin session inspection and revocation for other users
- admin single-user updates, including `must_change_password`
- admin bulk password-change flagging
- audit-log browsing for authorized admin users

### Resources

`app/api/resources_*.py` exposes the project/form hierarchy:

- projects
- forms
- sections
- questions
- choices
- action triggers and action-execution history

The resources API is protected by JWT auth, route-level rate limiting, and RBAC checks.

### Conditions

`app/api/conditions.py` exposes:

- condition metadata and operator metadata
- single and batch condition testing
- cache metrics and invalidation
- usage and impact analysis
- monitoring snapshots
- presets import/export and upsert
- approval transitions and rollback
- version history, restore, and record
- bulk create/update/delete/validate/test/import/export
- async evaluation and async job status

### UI templates

`app/api/ui_templates.py` stores theme and layout templates, plus revisions that can be published independently.

### Enterprise

`app/api/enterprise.py` exposes production hardening and SaaS administrative systems:

- Interactive Form Preview simulator
- Logic Layer step-by-step Dry-Run calculation simulator
- Tamper-Evident Signed Audit Trails and verification chains
- Dynamic role-based field masking and anonymization
- Offline key negotiation and validated sync queues
- Workspace collaboration presence tracking and draft locks
- Data lifecycle governance configurations and retention purge triggers
- Webhook policy setup and delivery analytics
- Platform operations dashboard metrics and security analytics

## Runtime components

- `app.wsgi:app` is the WSGI entry point
- `app.openapi:create_openapi_app()` builds the Flask/OpenAPI application
- `app.celery.worker` provides the Celery worker app
- `app.celery.tasks` includes periodic password-expiry enforcement
- `docker-compose.yml` runs API, MongoDB, Redis, worker, and optional beat

## Source-of-truth files

- `app/config.py` for configuration and validation
- `app/models/` for durable data structures
- `app/services/` for business logic
- `app/api/` for route behavior
- `tests/` for behavior guarantees and regressions
