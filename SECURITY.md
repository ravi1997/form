# Security

## Authentication Model

The service uses **HS256 JWT** with a dual-token strategy:

- **Access token** — short-lived (default 30 min), passed as `Authorization: Bearer <token>` on every request.
- **Refresh token** — long-lived (default 7 days), used only to issue new token pairs via `POST /api/v1/auth/refresh`.

### Session binding

Every token pair is bound to a `UserSession` record stored in MongoDB. A session tracks:

- `refresh_jti` — the JTI of the currently-valid refresh token.
- `refresh_token_hash` — SHA-256 of the raw refresh token string.
- `is_active` — revoked sessions reject both token types.

This means even if an access token is captured, an attacker cannot create a new session without the matching refresh token *and* the session must still be active.

### Token revocation

Refresh tokens are revoked by:
1. Adding the JTI + hash to the `token_blocklist` collection (TTL-indexed, expires with the token).
2. Setting `UserSession.is_active = False`.

Access tokens are short-lived and not blocklisted individually — their TTL is the revocation window. Use short access token TTLs in sensitive deployments.

### Key rotation

Multiple signing keys are supported via `JWT_ADDITIONAL_KEYS=kid:secret,kid2:secret2`. The active key ID is `JWT_ACTIVE_KID`. New tokens are always signed with the active key; old tokens are still verified against all keys. This allows zero-downtime key rotation.

---

## Authorization (RBAC)

Roles are **per-organization** and stored on the `User` document:

```json
{ "roles": { "<org_id>": ["admin", "editor"] } }
```

Effective permission for a resource endpoint is determined by matching the user's org-scoped roles against the project's organizations. Global permissions (`is_super_admin`, `is_organisation_admin`) bypass scope checks.

See `app/api/resources_utils.py:ENDPOINT_PERMISSION` for the full permission map.

---

## Security Headers

Every HTTP response includes the following headers (set in `observability.py`):

| Header                          | Value                                                  |
|--------------------------------|--------------------------------------------------------|
| `X-Content-Type-Options`        | `nosniff`                                             |
| `X-Frame-Options`               | `DENY`                                                |
| `Referrer-Policy`               | `no-referrer`                                         |
| `X-XSS-Protection`              | `0` (browser XSS filter deprecated)                   |
| `Permissions-Policy`            | camera, microphone, geolocation denied                |
| `Content-Security-Policy`       | `default-src 'none'; frame-ancestors 'none'; ...`     |
| `Strict-Transport-Security`     | `max-age=31536000; includeSubDomains` (HTTPS only)    |

---

## CORS

Set `CORS_ALLOW_ORIGINS` to a comma-separated list of allowed origins. An empty value (the default) disables CORS headers entirely.

```
CORS_ALLOW_ORIGINS=https://app.example.com,https://admin.example.com
```

Using `*` allows all origins but disables `Access-Control-Allow-Credentials`.

---

## Rate Limiting

### Auth endpoints

Auth endpoints (login, refresh, logout) use MongoDB-backed bucket counters (`RateLimitCounter`) with configurable limits:

| Variable                              | Default |
|--------------------------------------|---------|
| `AUTH_RATE_LIMIT_LOGIN_MAX`           | 10 / 60s |
| `AUTH_RATE_LIMIT_REFRESH_MAX`         | 20 / 60s |
| `AUTH_RATE_LIMIT_LOGOUT_MAX`          | 20 / 60s |

### General API

The resource API uses a priority-based `RateLimitService` backed by Redis (with in-memory fallback). Rules are stored in `rate_limit_configs` and manageable via the `/api/v1/rate-limits` admin API.

All 429 responses include:
- `Retry-After` header (seconds until window resets)
- `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset` headers

---

## Input Validation

All request bodies are validated by **Pydantic v2** models before reaching route handlers. flask-openapi3 rejects malformed bodies with a 422 response before the handler is invoked.

---

## Sensitive Data Handling

The `RotatingLoggerService` masks sensitive fields in request/response logs:

- `authorization`, `cookie`, `set-cookie`, `x-api-key`
- `password`, `token`, `refresh_token`, `access_token`, `secret`, `client_secret`
- Any key containing `password`, `secret`, `token`, or `key` (case-insensitive)

Masked values appear as `[MASKED]` in log files.

Password hashes are stored using **Werkzeug's `generate_password_hash`** (pbkdf2-sha256 by default).

---

## Condition Evaluator Sandboxing

The `safe_dsl.py` arithmetic evaluator only allows a restricted set of operations and functions (`sum`, `average`, `min`, `max`, `count`, etc.). It does not use `eval()` on untrusted input.

---

## Known Limitations

1. **Access token revocation**: Access tokens are not individually revokable; they remain valid until expiry after logout. Mitigate with short `JWT_ACCESS_TOKEN_EXPIRES_MINUTES` values (≤15 min in high-security deployments).

2. **`@rate_limit` decorator on flask-openapi3 routes**: The `@rate_limit` decorator in `app/middleware/rate_limit.py` is designed for standard Flask routes. When stacked above a flask-openapi3 `@blueprint.post()` decorator, flask-openapi3 registers the route at decoration time before the rate limit wrapper is applied. The decorator becomes a no-op on those routes. Auth endpoint rate limiting is enforced through the MongoDB bucket counter mechanism in `app/services/security.py` instead.

3. **In-memory rate limit fallback**: If Redis is unavailable, the `RateLimitService` falls back to an in-process dictionary. This is not distributed — each worker process has its own counter. Use Redis in multi-worker production deployments.

4. **Refresh token revocation delay**: When `revoke_all_sessions` is called (e.g., logout-all), existing access tokens for those sessions remain valid until they expire naturally.

---

## Responsible Disclosure

If you discover a security vulnerability, please report it privately by creating a GitHub Security Advisory rather than opening a public issue.
