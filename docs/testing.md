# Testing

## Primary tools

- Pytest for unit, integration, and Celery regression coverage
- Ruff for formatting and lint checks
- Mypy for type checking

## Commands

```bash
pytest -q
pytest --cov=app --cov-report=term
make test
make lint
make type-check
```

## Test focus

- Auth and session lifecycle
- Configuration parsing and validation
- RBAC and security checks
- Condition evaluation and caching
- Logging and observability behavior
- Celery worker behavior
