# Form Service API

Form Service API is a Flask + OpenAPI backend for form/resource management, JWT session auth, hierarchical form editing, condition evaluation, rate limiting, password-expiry enforcement, and Celery-backed async work. It uses MongoDB through MongoEngine and Redis for Celery and distributed rate limiting. New registrations create unverified accounts only; usable sessions are issued after verification or a successful login.

## Documentation

- [Overview](docs/overview.md)
- [Architecture](docs/architecture.md)
- [Installation](docs/installation.md)
- [Development](docs/development.md)
- [Configuration](docs/configuration.md)
- [Environment variables](docs/environment-variables.md)
- [API overview](docs/api/overview.md)
- [API authentication](docs/api/authentication.md)
- [API endpoints](docs/api/endpoints.md)
- [Database models](docs/database/models.md)
- [Database migrations and indexes](docs/database/migrations.md)
- [Security model](docs/security/security-model.md)
- [Deployment: production](docs/deployment/production.md)
- [Deployment: Docker](docs/deployment/docker.md)
- [Deployment: CI/CD](docs/deployment/ci-cd.md)
- [Testing](docs/testing.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Contributing](docs/contributing.md)
- [Coding standards](docs/coding-standards.md)
- [Architecture decisions](docs/decisions/architecture-decisions.md)

## Quick start

```bash
pip install -r requirements.txt -r requirements-test.txt
cp .env.example .env
pytest -q
gunicorn --bind 0.0.0.0:8000 app.wsgi:app
```

For Docker-based development, keep the same `.env` file in the project root and
run:

```bash
make docker-dev
make docker-status-all
```

Compose reads `.env` from the project root and uses it for container
configuration. The local override adds the source mount and development-specific
settings.

## Common commands

```bash
make install
make test
make lint
make format
make type-check
make docker-dev
make docker-prod
make docker-status-all
make docker-rebuild-clean
```

The OpenAPI document is served from `/openapi.json`, and the API is mounted under `/api/v1`.

## Docker notes

- `docker-compose.yml` defines the full stack
- `docker-compose.override.yml` applies local development behavior
- `.env.example` is the template for your project-root `.env`
- `docker-status-all` may report a transient app reset during the first few
  seconds after startup; re-run `make docker-health` if that happens
