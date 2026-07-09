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

## Test layers

### Unit tests

- config parsing and validation
- auth token/session helpers
- RBAC and permission helpers
- condition evaluator logic
- logging service behavior
- cache correctness

### Integration tests

- auth endpoints
- resource endpoints
- condition APIs
- UI template flows
- rate limit service behavior

### Celery tests

- worker bootstrap
- task registration
- async condition job behavior

## Regression focus

- auth and session lifecycle
- configuration parsing and validation
- RBAC and security checks
- condition evaluation and caching
- logging and observability behavior
- Celery worker behavior

## How to choose a test command

- use a targeted file first when working on one module
- run the full suite before merging
- run `make lint` and `make type-check` whenever touching shared helpers or schemas
