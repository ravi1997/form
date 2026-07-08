# Form Service API

Production-ready Flask OpenAPI service for form/resource management, auth/session lifecycle, condition evaluation, rate limiting, and UI template management backed by MongoDB.

## Features

- OpenAPI endpoints under `/api/v1`
- JWT auth with refresh token rotation and session tracking
- Role-based access control for resource APIs
- Condition evaluation, preset/version workflows
- Structured rotating logs with request correlation IDs
- Health, liveness, readiness, and metrics endpoints
- Configurable rate limiting and audit logging
- Docker and docker-compose support

## Architecture overview

- `app/openapi.py`: application factory + middleware/bootstrap wiring
- `app/api/*`: API surface grouped by domain (`auth`, `resources`, `conditions`, `rate_limit`, `ui_templates`, `health`)
- `app/api/resources_schemas.py`: extracted path/query/response schema contracts for resources endpoints
- `app/models/*`: MongoEngine persistence models
- `app/services/*`: domain services (auth, RBAC, conditions, rate limiting, security, logging)
- `app/middleware/*`: request ID, observability headers/metrics, rotating request/response logging, rate-limit decorators

## Quick start (local)

```bash
python -m pip install -r requirements.txt -r requirements-test.txt
cp .env.example .env
pytest -q --cov=app --cov-report=term
gunicorn --bind 0.0.0.0:8000 app.wsgi:app
```

## Required environment variables

- `APP_ENV` (`development` / `production`)
- `MONGODB_URI` (required in production)
- `MONGODB_DB`
- `JWT_SECRET_KEY` (required in production)
- `JWT_ACTIVE_KID`

Optional:

- `JWT_ADDITIONAL_KEYS`
- `LOG_LEVEL`, `LOG_DIR`, `LOG_MAX_BYTES`, `LOG_BACKUP_COUNT`
- `CORS_ALLOW_ORIGINS` (comma-separated)
- `ENABLE_COMPRESSION`
- `REQUEST_ID_HEADER`
- auth/resource rate limit settings from `.env.example`

## Health and observability endpoints

- `GET /api/v1/health`
- `GET /api/v1/liveness`
- `GET /api/v1/readiness`
- `GET /api/v1/metrics`

## Docker

Build:

```bash
docker build -t form-service:latest .
```

Run with compose:

```bash
export JWT_SECRET_KEY='replace-me'
docker compose up --build
```

The service is exposed on `http://localhost:8000`.

## CI

GitHub Actions workflow runs:

- Ruff lint
- Mypy type checks
- Pytest suite
- `pip-audit` vulnerability checks
- Docker image build verification

## Troubleshooting

- **Mongo connection errors**: verify `MONGODB_URI`/`MONGODB_DB` and database availability.
- **401/403 errors**: verify bearer token type (`access`) and RBAC roles/memberships.
- **429 errors**: inspect rate-limit configuration and logs.
- **Readiness degraded**: MongoDB ping failed; check DB service and network access.
