# Deployment Validation Checklist

Use this before production release.

## 1) Environment Variables

Required in production:

- `APP_ENV=production` (or equivalent alias)
- `JWT_SECRET_KEY` (strong secret)

Recommended explicit settings:

- `JWT_ALGORITHM`
- `JWT_ACTIVE_KID`
- `JWT_ADDITIONAL_KEYS` (during rotation windows)
- `JWT_ACCESS_TOKEN_EXPIRES_MINUTES`
- `JWT_REFRESH_TOKEN_EXPIRES_DAYS`
- `AUTH_RATE_LIMIT_LOGIN_MAX`
- `AUTH_RATE_LIMIT_LOGIN_WINDOW_SECONDS`
- `AUTH_RATE_LIMIT_REFRESH_MAX`
- `AUTH_RATE_LIMIT_REFRESH_WINDOW_SECONDS`
- `AUTH_RATE_LIMIT_LOGOUT_MAX`
- `AUTH_RATE_LIMIT_LOGOUT_WINDOW_SECONDS`
- `RESOURCE_RATE_LIMIT_MAX`
- `RESOURCE_RATE_LIMIT_WINDOW_SECONDS`
- `ENABLE_AUDIT_LOGS`
- `REQUEST_ID_HEADER`
- `API_VERSION`
- `AUDIT_LOG_RETENTION_DAYS`

## 2) Startup Logs

On app startup, verify logs include:

- selected config class (`Config loaded: ProductionConfig`)
- sanitized config snapshot (`Config snapshot: ...`)

Ensure snapshot confirms:

- `env_name: production`
- expected TTL/rate-limit values
- `jwt_secret_configured: true`
- expected `jwt_active_kid`
- expected `request_id_header`

## 3) Admin Config Health Endpoint

Call endpoint:

```bash
curl -s "http://localhost:5000/api/v1/auth/admin/config/health" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

Validate response fields match deployment intent:

- `env_name`
- `debug`
- JWT TTL values
- rate limits
- resource API rate limits
- `enable_audit_logs`
- `audit_log_retention_days`
- `jwt_active_kid`
- `jwt_additional_key_ids`
- `request_id_header`
- `api_version`

## 4) Auth and Throttle Smoke Tests

- Login success path
- Refresh success path
- Logout success path
- Trigger throttling and verify:
  - HTTP 429
  - `Retry-After`
  - `limit_scope` in payload

## 5) Audit Search Endpoint Checks

- `GET /api/v1/auth/admin/audit-logs`
- `GET /api/v1/auth/admin/audit-logs/search`
- Validate page mode and cursor mode both work
- Confirm filters (user/action/date range) return expected subsets

## 6) Mongo Query Plans

Run explain plans from docs/auth-operations.md and verify indexed execution.

## 7) Security Posture

- HTTPS enabled at edge/load balancer
- trusted proxy configuration reviewed for correct client IP parsing
- secrets managed through secure secret storage
- no development fallback secrets in production

## 8) Key Rotation Readiness

- Follow the phased procedure in `docs/jwt-key-rotation.md`
- Ensure old keys are present in `JWT_ADDITIONAL_KEYS` only during overlap windows
- Remove retired keys after refresh token TTL window
