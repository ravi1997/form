# Repository Guidelines

## Project Structure & Module Organization

- `app/` contains the Flask API, Celery integration, services, models, middleware, and schemas.
- `tests/` holds unit, integration, and Celery regression tests. Use `tests/celery/` for worker-specific coverage.
- `docs/` contains operational docs such as `CELERY_OPERATIONS.md` and alerting guidance.
- `dashboards/` stores Grafana JSON dashboards.
- `docker-compose.yml`, `Dockerfile`, and `.github/workflows/ci.yml` define runtime and CI behavior.

## Build, Test, and Development Commands

- `make up` starts the full stack in Docker.
- `make down` stops the stack.
- `make test` runs the test suite inside the containerized environment.
- `make lint` runs Ruff checks.
- `make format` applies code formatting.
- `make build` rebuilds the application image.
- For direct verification, use `docker compose up -d --build app mongo redis worker` and check `GET /api/v1/health` and `GET /api/v1/ready`.

## Coding Style & Naming Conventions

- Use Python 3.12+, 4-space indentation, and type hints for public functions where practical.
- Prefer descriptive snake_case for functions, variables, and module names.
- Keep service logic in `app/services/` and route handlers thin in `app/api/`.
- Run Ruff before committing; do not bypass lint or formatting failures.

## Testing Guidelines

- Pytest is the main test framework.
- Add regression tests for bug fixes and behavior changes.
- Name tests to describe behavior, e.g. `test_retry_behavior` or `test_job_state_updates`.
- Run targeted tests alongside the full suite when touching Celery, auth, or configuration code.

## Commit & Pull Request Guidelines

- Use short, imperative commit messages, e.g. `feat: switch async execution to Celery worker`.
- Keep commits focused: code, docs, and tests should match the same change.
- PRs should summarize the problem, the fix, and the validation performed.

## Security & Configuration Notes

- Never commit secrets; use `.env.example` as the reference for required variables.
- Production compose deployments require MongoDB, Redis, JWT settings, and Celery broker/result backend configuration.
