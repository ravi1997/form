# Form Service API

Form Service API is a Flask + OpenAPI backend for form/resource management, JWT session auth, hierarchical form editing, condition evaluation, rate limiting, and Celery-backed async work. It uses MongoDB through MongoEngine and Redis for Celery and distributed rate limiting.

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

## Common commands

```bash
make install
make test
make lint
make format
make type-check
make up
make down
```

The OpenAPI document is served from `/openapi.json`, and the API is mounted under `/api/v1`.
