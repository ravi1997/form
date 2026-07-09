# Development

## Useful commands

- `make install` installs runtime and test dependencies
- `make test` runs pytest with coverage
- `make lint` runs Ruff
- `make format` formats and fixes with Ruff
- `make type-check` runs mypy
- `make up` starts the compose stack
- `make logs` follows app and worker logs

## Workflow

1. Make the code change.
2. Run the targeted test file or command that exercises the change.
3. Run the relevant quality gates, usually `make lint`, `make type-check`, and `make test`.
4. Update docs when runtime behavior, configuration, or endpoints change.

## Debugging tips

- Use `LOG_LEVEL=DEBUG` to surface detailed auth, RBAC, and query traces
- Check `/api/v1/metrics` for request and async queue snapshots
- Check `/api/v1/readiness` when MongoDB connectivity is in question
