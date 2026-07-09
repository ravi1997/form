# Environment Variables

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

## Auth and limits

| Variable | Purpose |
| --- | --- |
| `JWT_ACCESS_TOKEN_EXPIRES_MINUTES` | Access token lifetime |
| `JWT_REFRESH_TOKEN_EXPIRES_DAYS` | Refresh token lifetime |
| `AUTH_RATE_LIMIT_LOGIN_MAX` | Login rate window count |
| `AUTH_RATE_LIMIT_REFRESH_MAX` | Refresh rate window count |
| `AUTH_RATE_LIMIT_LOGOUT_MAX` | Logout rate window count |
| `RESOURCE_RATE_LIMIT_MAX` | Resource API request count |

## Ops and retention

| Variable | Purpose |
| --- | --- |
| `AUDIT_LOG_RETENTION_DAYS` | Audit log TTL window |
| `MONITORING_STATS_RETENTION_DAYS` | Condition monitoring TTL window |
| `CELERY_TASK_TIME_LIMIT` | Hard async task timeout |
| `CELERY_TASK_SOFT_TIME_LIMIT` | Soft async task timeout |
| `ENABLE_COMPRESSION` | Enables response compression |
| `REQUEST_ID_HEADER` | Request ID header name |
