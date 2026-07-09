# CI/CD

The repository ships with GitHub Actions in `.github/workflows/ci.yml`.

## Typical checks

- Ruff formatting and linting
- Mypy type checking
- Pytest suite with coverage
- Dependency vulnerability auditing
- Docker image build
- Compose smoke test against health and readiness endpoints
