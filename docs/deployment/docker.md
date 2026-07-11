# Docker Deployment

This repository uses Docker Compose to run the API, Celery worker, MongoDB, and
Redis together as a single local stack. The goal is to make the developer setup
and the production-style setup use the same image and the same configuration
shape, with only the environment values changing.

## Build

```bash
docker build -t form-service:latest .
```

The Dockerfile is used for both the API and worker containers. It builds a
single Python image that contains the application code and dependencies, then
the compose file chooses whether that image runs as the API server, the worker,
or the beat scheduler.

## Compose

```bash
cp .env.example .env
# edit .env with local or production values
docker compose up --build
```

Compose reads `.env` from the project root. That file is the source of truth for
container configuration values such as JWT secrets, MongoDB credentials, log
levels, Redis URLs, and Celery broker URLs.

Use `.env.example` as the template and keep the real `.env` file out of version
control.

## Recommended workflows

### Development

```bash
cp .env.example .env
make docker-dev
```

The development compose override:

- mounts the source tree into the app container
- sets `APP_ENV=development`
- points MongoDB at `form_dev`
- points Celery at the in-network Redis service

### Production-style local run

```bash
cp .env.example .env
make docker-prod
```

This uses the base compose file without the local source mount. It is the
closest local approximation to the production container layout.

### First-time bootstrap

```bash
make docker-bootstrap
```

This will:

- create `.env` if it is missing
- render the Compose config
- start the stack in detached mode

## Compose services

- `app`
  - runs the Flask/OpenAPI application through Gunicorn
  - listens on port `8000`
  - serves `/api/v1/health` for readiness checks
  - mounts `app_logs` for rotating log files

- `worker`
  - runs `celery -A app.celery.worker worker --loglevel=info`
  - consumes tasks from the `form_tasks` queue
  - uses the in-network Redis broker and result backend

- `beat`
  - runs `celery -A app.celery.worker beat --loglevel=info`
  - is gated behind the `scheduler` profile in the base compose file

- `mongo`
  - uses `mongo:8`
  - stores data in the `mongo_data` volume
  - accepts the root credentials from `.env`

- `redis`
  - uses `redis:7-alpine`
  - persists append-only file data in `redis_data`
  - provides Celery broker, result-backend storage, and the distributed rate-limit backend

## Local override behavior

`docker-compose.override.yml` is intended for local development and changes only
the parts that should differ in day-to-day work:

- it mounts the repo into `/app`
- it sets development environment values
- it points MongoDB at the development database
- it forces Celery and rate limiting to use `redis://redis:6379/0` and `redis://redis:6379/1`

The override still consumes the same `.env` file, so the secrets and tunables
stay centralized.

## Docker make targets

The `Makefile` includes grouped commands for common Docker tasks:

- `make docker-env`
- `make docker-config`
- `make docker-pull`
- `make docker-start`
- `make docker-start-all`
- `make docker-dev`
- `make docker-prod`
- `make docker-up-dev`
- `make docker-up-prod`
- `make docker-stop`
- `make docker-restart`
- `make docker-reset`
- `make docker-rebuild-clean`
- `make docker-status-all`
- `make docker-health`
- `make docker-health-all`
- `make docker-follow`
- `make docker-logs-all`
- `make docker-shell-app`
- `make docker-shell-worker`
- `make docker-shell-beat`
- `make docker-clean`
- `make docker-clean-all`

The most useful composites are:

- `docker-bootstrap` for first-time setup
- `docker-dev` for local iteration
- `docker-prod` for production-style startup
- `docker-rebuild-clean` for a full reset and rebuild
- `docker-status-all` for a quick read of stack health and logs

## Health checks

- app health check probes `/api/v1/health`
- MongoDB health check uses `mongosh ... ping`
- Redis health check uses `redis-cli ping`

The app health probe is intentionally light. During startup it can report a
transient connection reset before the service fully settles. If that happens,
wait a few seconds and run `make docker-health` again.

## Persistent volumes

- `mongo_data` stores MongoDB data
- `redis_data` stores Redis data
- `app_logs` stores rotating log files

If you change MongoDB credentials in `.env`, the existing `mongo_data` volume
can keep the old user database. In that case, remove the volume and recreate the
stack so MongoDB initializes with the new values.
