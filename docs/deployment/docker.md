# Docker Deployment

## Build

```bash
docker build -t form-service:latest .
```

The Dockerfile is used for both the API and worker containers.

## Compose

```bash
export JWT_SECRET_KEY=change-me
export MONGO_INITDB_ROOT_PASSWORD=change-me-too
docker compose up --build
```

## Compose services

- `app` uses the API entry point
- `worker` uses `celery -A app.celery.worker worker --loglevel=info`
- `beat` uses `celery -A app.celery.worker beat --loglevel=info`
- `mongo` binds all interfaces and uses auth
- `redis` persists AOF data

## Local override behavior

`docker-compose.override.yml` is intended for local development and sets a development environment, mounts the source tree, and points at a dev database.

## Health checks

- app health check probes `/api/v1/health`
- MongoDB health check uses `mongosh ... ping`
- Redis health check uses `redis-cli ping`

## Persistent volumes

- `mongo_data` stores MongoDB data
- `redis_data` stores Redis data
- `app_logs` stores rotating log files
