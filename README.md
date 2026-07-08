# Form Service API

Production-ready Flask OpenAPI service for form/resource management, auth/session lifecycle, condition evaluation, rate limiting, and UI template management backed by MongoDB.

## Features

- OpenAPI 3 endpoints under `/api/v1` with Pydantic v2 schema validation
- JWT auth with refresh token rotation, session tracking, and token blocklisting
- Role-based access control (per-organisation roles)
- Hierarchical form structures: Project → Form → Section → Question → Choice
- Form workflow state machine with configurable approval gates
- Condition evaluation engine (8 types: regex, comparison, logical, temporal, arithmetic, set, dsl, custom)
- Condition management: presets, versioning, approval workflow, async evaluation, monitoring
- Structured rotating log files with `X-Request-Id` correlation throughout
- Health, liveness, readiness, and metrics endpoints
- Configurable rate limiting (MongoDB counters + Redis/in-memory tiers)
- Full audit logging with configurable TTL-based retention
- Docker and docker-compose support

## Documentation

| Document | Description |
|----------|-------------|
| [ARCHITECTURE.md](ARCHITECTURE.md) | System architecture, request flow, data model, component interactions |
| [DEVELOPMENT.md](DEVELOPMENT.md) | Local setup, debugging, IDE setup, conventions |
| [DEPLOYMENT.md](DEPLOYMENT.md) | Docker, production checklist, Kubernetes probes, JWT key rotation |
| [SECURITY.md](SECURITY.md) | Security model, headers, rate limiting, known limitations |
| [TESTING.md](TESTING.md) | Test strategy, fixtures, writing tests, coverage |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Branch naming, commit conventions, PR process |
| [CHANGELOG.md](CHANGELOG.md) | Change history |
| [.env.example](.env.example) | All environment variables with descriptions |

## Quick start (local)

```bash
# Install dependencies
pip install -r requirements.txt -r requirements-test.txt

# Configure
cp .env.example .env          # edit as needed

# Run tests (no MongoDB required — uses mongomock)
pytest -q --cov=app --cov-report=term

# Start the server (requires MongoDB)
gunicorn --bind 0.0.0.0:8000 app.wsgi:app
```

Or use the Makefile:

```bash
make install    # install deps
make test       # run test suite with coverage
make lint       # ruff check
make type-check # mypy
make docker-up  # docker compose up --build -d
```

## Required environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `APP_ENV` | No | `development` (default) / `production` |
| `MONGODB_URI` | Production | MongoDB connection string |
| `MONGODB_DB` | Production | Database name |
| `JWT_SECRET_KEY` | Production | Signing secret (≥32 random bytes) |
| `JWT_ACTIVE_KID` | No | Key ID for JWT signing (default: `v1`) |

See `.env.example` for the full list of optional settings.

## API endpoints (summary)

| Group | Base path | Description |
|-------|-----------|-------------|
| System | `/api/v1/health` `/liveness` `/readiness` `/metrics` | Health and observability |
| Auth | `/api/v1/auth` | Register, login, refresh, logout, sessions, admin |
| Resources | `/api/v1/projects` `/forms` `/sections` `/questions` `/choices` | Form hierarchy CRUD |
| Conditions | `/api/v1/conditions` | Condition test, cache, presets, versioning, monitoring |
| Rate limits | `/api/v1/rate-limits` | Rate limit rule management |
| UI templates | `/api/v1/ui-templates` | Layout and theme templates |

The OpenAPI schema is served at `/openapi.json` by flask-openapi3.

## Docker

```bash
docker build -t form-service:latest .
export JWT_SECRET_KEY='replace-me'
docker compose up --build
```

The service is exposed on `http://localhost:8000`. See [DEPLOYMENT.md](DEPLOYMENT.md) for production guidance.

## CI

GitHub Actions (`.github/workflows/ci.yml`) runs on every push:

1. Ruff lint
2. Mypy type checks
3. Pytest suite (324 tests, mongomock)
4. Coverage artifact upload
5. `pip-audit` vulnerability scan
6. Docker image build
7. Docker Compose smoke test (health, readiness, metrics)

## Troubleshooting

- **MongoDB connection errors**: verify `MONGODB_URI`/`MONGODB_DB` and database availability.
- **401/403 errors**: verify the `Authorization: Bearer <token>` header is an *access* token (not refresh), and that the user has the required RBAC role for the endpoint.
- **429 errors**: inspect the `Retry-After` response header and rate-limit configuration in `rate_limit_configs`.
- **Readiness 503**: MongoDB `ping` failed — check the DB service and network connectivity.
- **Verbose logs**: set `LOG_LEVEL=DEBUG` to see detailed JWT decode, DB query, and RBAC trace entries.

