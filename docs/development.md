# Development

## Useful commands

- `make install` installs runtime, test, and local tooling dependencies
- `make test` runs pytest with coverage
- `make lint` runs Ruff
- `make format` formats and fixes with Ruff
- `make type-check` runs mypy
- `make docker-env` creates `.env` from `.env.example` if it is missing
- `make docker-dev` starts the local development compose stack with the override file
- `make docker-prod` starts the production-style stack from the base compose file
- `make docker-bootstrap` creates `.env`, validates compose, builds, and starts the stack
- `make docker-rebuild-clean` forces a clean rebuild and restarts the stack
- `make docker-status-all` shows compose status, recent logs, and an app health probe
- `make docker-health` checks the app readiness endpoint
- `make docker-log-app`, `make docker-log-worker`, `make docker-log-mongo`, and `make docker-log-redis` stream service-specific logs
- `make docker-shell-app`, `make docker-shell-worker`, and `make docker-shell-beat` open shells inside the running containers

## Workflow

1. Make the code change.
2. Run the targeted test file or command that exercises the change.
3. Run the relevant quality gates, usually `make lint`, `make type-check`, and `make test`.
4. Update docs when runtime behavior, configuration, or endpoints change.

## Docker Development Flow

This repository uses Docker Compose as the primary developer workflow when the
full stack is needed.

1. Copy the example environment file:

```bash
cp .env.example .env
```

2. Edit `.env` with your local values.

Required values for Docker-based runs:

- `JWT_SECRET_KEY`
- `MONGO_INITDB_ROOT_PASSWORD`

Common Docker-oriented values:

- `APP_ENV=development`
- `MONGODB_URI=mongodb://formadmin:<password>@mongo:27017/form_dev?authSource=admin`
- `CELERY_BROKER_URL=redis://redis:6379/0`
- `CELERY_RESULT_BACKEND=redis://redis:6379/1`

3. Start the dev stack:

```bash
make docker-dev
```

4. Check readiness:

```bash
make docker-status-all
```

5. If you need to rebuild from scratch:

```bash
make docker-rebuild-clean
```

Notes:

- `docker-compose.yml` is the base stack.
- `docker-compose.override.yml` applies the development mount and dev-specific
  environment values.
- The app and worker containers both use the same built image.
- Redis and MongoDB are long-lived services with persistent volumes.
- The app health probe can report a transient reset while the container is still
  starting; re-run `make docker-health` after a short delay if needed.

## Debugging tips

- Use `LOG_LEVEL=DEBUG` to surface detailed auth, RBAC, and query traces
- Check `/api/v1/metrics` for request and async queue snapshots
- Check `/api/v1/readiness` when MongoDB connectivity is in question
- If Celery shows `localhost` in its transport URL, verify that the compose
  override is in effect and that the container was restarted after the update.
- If MongoDB authentication fails after changing credentials, remove the Mongo
  volume with `make docker-clean-volumes` or `make docker-clean-all` and
  recreate the stack.
