# Environment Variables

The application reads its configuration from environment variables, and Docker
Compose loads those values from the project-root `.env` file. The same variable
names are used whether you run the app directly or inside containers.

## Core variables

| Variable | Purpose |
| --- | --- |
| `APP_ENV` | Selects development, staging, qa, or production-style config |
| `JWT_SECRET_KEY` | Active JWT signing secret |
| `JWT_ACTIVE_KID` | Key ID for the active signing key |
| `JWT_ADDITIONAL_KEYS` | Older `kid:secret` values for rotation |
| `MONGODB_URI` | MongoDB connection string |
| `MONGODB_DB` | Database name |
| `CELERY_BROKER_URL` | Redis broker URL |
| `CELERY_RESULT_BACKEND` | Redis result backend URL |
| `LOG_LEVEL` | Application log level |
| `LOG_DIR` | Directory for rotating logs |
| `CORS_ALLOW_ORIGINS` | Allowed browser origins |
| `MONGO_INITDB_ROOT_USERNAME` | MongoDB root username used by the container |
| `MONGO_INITDB_ROOT_PASSWORD` | MongoDB root password used by the container |

## JWT variables

| Variable | Purpose |
| --- | --- |
| `JWT_ALGORITHM` | JWT signing algorithm, currently `HS256` |
| `JWT_ACCESS_TOKEN_EXPIRES_MINUTES` | Access token TTL |
| `JWT_REFRESH_TOKEN_EXPIRES_DAYS` | Refresh token TTL |

## Auth and limits

| Variable | Purpose |
| --- | --- |
| `JWT_ACCESS_TOKEN_EXPIRES_MINUTES` | Access token lifetime |
| `JWT_REFRESH_TOKEN_EXPIRES_DAYS` | Refresh token lifetime |
| `AUTH_RATE_LIMIT_LOGIN_MAX` | Login rate window count |
| `AUTH_RATE_LIMIT_REFRESH_MAX` | Refresh rate window count |
| `AUTH_RATE_LIMIT_LOGOUT_MAX` | Logout rate window count |
| `RESOURCE_RATE_LIMIT_MAX` | Resource API request count |
| `RESOURCE_RATE_LIMIT_WINDOW_SECONDS` | Resource API rate-limit window |
| `RESOURCE_RBAC_REQUIRE_ORG_ROLE_ALIGNMENT` | Require org-role alignment for project access |
| `WORKFLOW_STRICT_REVIEW_BEFORE_APPROVE` | Enforce review before approval in form workflow |
| `ENABLE_AUDIT_LOGS` | Enable or disable security/audit event logging |
| `RATE_LIMIT_FAIL_OPEN` | Fail open when the Redis rate limiter is unavailable |

## Ops and retention

| Variable | Purpose |
| --- | --- |
| `AUDIT_LOG_RETENTION_DAYS` | Audit log TTL window |
| `MONITORING_STATS_RETENTION_DAYS` | Condition monitoring TTL window |
| `CELERY_TASK_TIME_LIMIT` | Hard async task timeout |
| `CELERY_TASK_SOFT_TIME_LIMIT` | Soft async task timeout |
| `ENABLE_COMPRESSION` | Enables response compression |
| `REQUEST_ID_HEADER` | Request ID header name |
| `API_VERSION` | Exposed API version string |

## Logging and database

| Variable | Purpose |
| --- | --- |
| `LOG_LEVEL` | Root application log level |
| `LOG_DIR` | Path used by the rotating logger |
| `LOG_MAX_BYTES` | Maximum size of one log file before rotation |
| `LOG_BACKUP_COUNT` | Number of rotated log files to retain |
| `MONGODB_CONNECT_TIMEOUT_MS` | MongoDB connection timeout budget |

## Docker-specific guidance

When running under Docker Compose:

- `MONGODB_URI` should point at `mongo:27017` inside the compose network
- `CELERY_BROKER_URL` should point at `redis:6379` inside the compose network
- `CELERY_RESULT_BACKEND` should point at `redis:6379` inside the compose network
- `LOG_DIR` should usually stay `/app/logs`
- `APP_ENV=development` is used by `docker-compose.override.yml`
- `APP_ENV=production` is used by the base compose file

If you switch MongoDB credentials after the volume has been created, remove the
`mongo_data` volume before restarting so the container can reinitialize cleanly.

## Example production set

```bash
APP_ENV=production
JWT_SECRET_KEY=<strong-random-secret>
JWT_ACTIVE_KID=v1
MONGODB_URI=mongodb://formadmin:<password>@mongo:27017/form_prod?authSource=admin
MONGODB_DB=form_prod
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/1
LOG_LEVEL=INFO
```
