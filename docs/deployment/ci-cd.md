# CI/CD

The repository ships with GitHub Actions in `.github/workflows/ci.yml`.

## Typical checks

- Ruff formatting and linting
- Mypy type checking
- Pytest suite with coverage
- Dependency vulnerability auditing
- Docker image build
- Compose smoke test against health, readiness, and metrics endpoints

## What the pipeline is meant to prove

- the Python sources parse and type-check
- the API still boots under the container image
- the application still answers basic operational probes
- the dependency set is not obviously vulnerable
- the runtime image is buildable from the repository root

## Practical guidance

- keep docs and tests updated with behavior changes
- do not merge a change that affects runtime behavior without a matching regression test
- if a new endpoint changes routing or auth, update the API docs and the smoke tests together
