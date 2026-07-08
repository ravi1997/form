# Deployment Guide

## Docker (recommended)

### Build

```bash
docker build -t form-service:latest .
```

The Dockerfile uses a **two-stage build**:
1. **Builder stage** — compiles wheels from `requirements.txt`.
2. **Runtime stage** — installs from pre-built wheels, runs as a non-root `app` user.

### Run with Docker Compose

```bash
# Required: set the JWT secret in your environment or a .env file
export JWT_SECRET_KEY='your-strong-secret-here'
export JWT_ACTIVE_KID='v1'

docker compose up --build
```

The service binds to `http://localhost:8000`. MongoDB data is persisted in the `mongo_data` volume and log files in the `app_logs` volume.

#### Development override

`docker-compose.override.yml` is automatically applied when running `docker compose` locally. It sets `APP_ENV=development`, mounts the source tree into the container, and points at a dev database.

### Environment variables for Docker

At minimum, provide at runtime:

```
JWT_SECRET_KEY=<strong-random-secret>
JWT_ACTIVE_KID=v1
MONGODB_URI=mongodb://mongo:27017/form_prod
MONGODB_DB=form_prod
```

All other variables default to safe production values when `APP_ENV=production`.

---

## Production checklist

- [ ] `APP_ENV=production`
- [ ] `JWT_SECRET_KEY` set to a cryptographically random value (≥32 bytes)
- [ ] `MONGODB_URI` pointing to a secured MongoDB instance
- [ ] `CORS_ALLOW_ORIGINS` restricted to known frontend origins
- [ ] TLS termination at the load balancer / reverse proxy
- [ ] Log directory (`LOG_DIR`) mounted to persistent storage
- [ ] MongoDB authentication enabled
- [ ] MongoDB network access restricted to the application containers
- [ ] Redis configured for distributed rate limiting (optional but recommended for multi-worker)
- [ ] `LOG_LEVEL=INFO` (not DEBUG — avoids verbose debug output in production)

---

## Gunicorn configuration

The container uses:

```
gunicorn \
  --bind 0.0.0.0:8000 \
  --workers 2 \
  --threads 4 \
  --timeout 60 \
  --graceful-timeout 30 \
  --access-logfile - \
  --error-logfile - \
  app.wsgi:app
```

Adjust `--workers` to `(2 × CPU cores) + 1` for CPU-bound workloads. Because MongoEngine connections are per-process, each worker opens its own connection pool.

---

## Health checks

| Endpoint                  | Returns                             | Use for          |
|--------------------------|-------------------------------------|------------------|
| `GET /api/v1/health`      | `{"status":"ok"}`                  | Load balancer    |
| `GET /api/v1/liveness`    | `{"status":"alive"}`               | Kubernetes liveness probe |
| `GET /api/v1/readiness`   | `{"status":"ready","database":"ok"}` or 503 | Kubernetes readiness probe |
| `GET /api/v1/metrics`     | Request/duration stats             | Monitoring       |

Kubernetes example:

```yaml
livenessProbe:
  httpGet:
    path: /api/v1/liveness
    port: 8000
  initialDelaySeconds: 10
  periodSeconds: 15

readinessProbe:
  httpGet:
    path: /api/v1/readiness
    port: 8000
  initialDelaySeconds: 5
  periodSeconds: 10
  failureThreshold: 3
```

---

## MongoDB indexes

Critical indexes are declared in `meta` blocks on each MongoEngine document and created automatically on first access. For production deployments, run index creation explicitly before routing traffic:

```bash
python scripts/setup_condition_indexes.py
```

Rate limit initial seed:

```bash
python scripts/init_rate_limits.py
```

---

## Logging

Log files rotate at `LOG_MAX_BYTES` (default 10 MB) and keep `LOG_BACKUP_COUNT` (default 10) backups. In containerised deployments, mount `LOG_DIR` to a persistent volume or configure a log aggregator to ship from the container path.

```yaml
volumes:
  - app_logs:/app/logs
```

Logs are structured JSON, one entry per line, suitable for forwarding to Elasticsearch, Loki, or any JSON-aware log aggregator.

---

## JWT key rotation

To rotate the JWT secret without invalidating existing sessions:

1. Add the current key to `JWT_ADDITIONAL_KEYS`:
   ```
   JWT_ADDITIONAL_KEYS=v1:old-secret
   ```
2. Set the new key as active:
   ```
   JWT_SECRET_KEY=new-strong-secret
   JWT_ACTIVE_KID=v2
   ```
3. New tokens are issued with `v2`. Existing `v1` tokens are still accepted until they expire.
4. After all `v1` tokens have expired, remove the old key from `JWT_ADDITIONAL_KEYS`.

---

## CI/CD

GitHub Actions workflow (`.github/workflows/ci.yml`) runs on every push and pull request:

1. **Lint** — `ruff check .`
2. **Type check** — `mypy app tests`
3. **Tests** — `pytest --cov=app --cov-report=xml`
4. **Coverage upload** — artifact saved as `coverage-xml`
5. **Vulnerability audit** — `pip-audit -r requirements.txt`
6. **Docker build** — verifies image builds successfully
7. **Smoke test** — `docker compose up`, hits `/health`, `/readiness`, `/metrics`
