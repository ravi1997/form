# Configuration

## Source of truth

- `.env.example` documents the supported environment variables and typical defaults
- `app/config.py` defines defaults, validation, and runtime snapshots
- `docker-compose.yml` shows the production container wiring used by the stack

## Environment selection

`APP_ENV` and `FLASK_ENV` are used to select a config class.

- `development`, `dev`, and `local` map to `DevelopmentConfig`
- `production`, `prod`, `stage`, `staging`, and `qa` map to `ProductionConfig`
- any unknown value falls back to `DevelopmentConfig`

## Config groups

### JWT

- `JWT_SECRET_KEY` is required in production
- `JWT_ACTIVE_KID` selects the signing key ID
- `JWT_ADDITIONAL_KEYS` accepts either JSON mapping or `kid:secret` pairs
- `JWT_ALGORITHM` must currently be `HS256`
- `JWT_ACCESS_TOKEN_EXPIRES_MINUTES` and `JWT_REFRESH_TOKEN_EXPIRES_DAYS` control token TTLs

### Auth and workflow

- `AUTH_RATE_LIMIT_LOGIN_MAX` and `AUTH_RATE_LIMIT_LOGIN_WINDOW_SECONDS`
- `AUTH_RATE_LIMIT_REFRESH_MAX` and `AUTH_RATE_LIMIT_REFRESH_WINDOW_SECONDS`
- `AUTH_RATE_LIMIT_LOGOUT_MAX` and `AUTH_RATE_LIMIT_LOGOUT_WINDOW_SECONDS`
- `RESOURCE_RATE_LIMIT_MAX` and `RESOURCE_RATE_LIMIT_WINDOW_SECONDS`
- `RESOURCE_RBAC_REQUIRE_ORG_ROLE_ALIGNMENT`
- `WORKFLOW_STRICT_REVIEW_BEFORE_APPROVE`
- `ENABLE_AUDIT_LOGS`

### Database

- `MONGODB_URI`
- `MONGODB_DB`
- `MONGODB_CONNECT_TIMEOUT_MS`

### Celery

- `CELERY_BROKER_URL`
- `CELERY_RESULT_BACKEND`
- `CELERY_TASK_DEFAULT_QUEUE`
- `CELERY_TASK_TIME_LIMIT`
- `CELERY_TASK_SOFT_TIME_LIMIT`
- `CELERY_TASK_ALWAYS_EAGER`
- `CELERY_TASK_EAGER_PROPAGATES`

### Logging and HTTP

- `LOG_LEVEL`
- `LOG_DIR`
- `LOG_MAX_BYTES`
- `LOG_BACKUP_COUNT`
- `REQUEST_ID_HEADER`
- `CORS_ALLOW_ORIGINS`
- `ENABLE_COMPRESSION`
- `API_VERSION`

### Retention

- `AUDIT_LOG_RETENTION_DAYS`
- `MONITORING_STATS_RETENTION_DAYS`

### Password policy

- `MAX_PASSWORD_EXPIRE_DAYS` controls how long a password can remain valid before the periodic policy task marks the user as requiring a reset

## Defaults by environment

### Development

- Access tokens last 60 minutes by default
- Login, refresh, and logout rate limits are higher than production
- Missing `JWT_SECRET_KEY` falls back to a development-only insecure secret with a warning
- MongoDB database defaults to `form_dev`

### Production

- Access tokens last 15 minutes by default
- Login, refresh, and logout rate limits are stricter
- `JWT_SECRET_KEY` is required
- `MONGODB_URI` or `MONGODB_SETTINGS` must be present
- `LOG_LEVEL` defaults to `INFO`
- Session cookies are marked secure, HTTP-only, and `SameSite=Lax`

## Validation behavior

- Unknown env keys beginning with `JWT_` or `AUTH_RATE_LIMIT_` are warned about in development and rejected in production
- Integer settings are range-checked
- `CELERY_TASK_SOFT_TIME_LIMIT` must be lower than `CELERY_TASK_TIME_LIMIT`
- `MAX_PASSWORD_EXPIRE_DAYS` must be a positive integer
- `API_VERSION` must match `v<number>`
- `JWT_ADDITIONAL_KEYS` must be a mapping
- `LOG_LEVEL` must be one of `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL`

## Runtime snapshot

`build_runtime_settings()` produces a runtime summary containing:

- environment name
- API version
- log configuration
- MongoDB connection settings
- monitoring retention
- request ID header
- CORS origins
- compression toggle
