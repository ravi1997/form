# Security Model

## Authentication

- JWT access and refresh tokens are signed with HS256
- `decode_token()` validates the token type, `kid`, signature, expiry, and claims
- Refresh tokens are tied to MongoDB session records
- Refresh token rotation is supported
- Refresh token revocation writes to `token_blocklist` and deactivates the session

## Session security

- Session state is stored in `user_sessions`
- `refresh_token_hash` is SHA-256 of the raw token string
- `refresh_jti` prevents token substitution across rotations
- Session audit events are stored in `session_audit_logs`

## Authorization

- Resource access is controlled with RBAC
- Roles are stored per organization
- `has_global_admin_privileges()` and related helpers distinguish global, org, and scoped admin access
- Resource route permissions are enforced in `app/api/resources_utils.py`
- Auth admin routes require elevated admin access

## Rate limiting

- Auth endpoints use MongoDB counters
- Resource endpoints use the generic rate-limit service
- Redis is preferred for distributed limits
- `RATE_LIMIT_FAIL_OPEN=true` means Redis failure returns a 503 response body rather than blowing up the handler

## Hardening

- Security and request headers are set by middleware
- Request IDs are propagated and logged
- Sensitive values are masked in rotating logs
- `CORS_ALLOW_ORIGINS` must be restricted in browser-facing deployments
- Condition DSL parsing rejects unsafe identifiers and `__` traversal

## Known security constraints

- Access tokens are not individually blocklisted; short TTLs are the main access-token revocation control
- In-memory rate-limit fallback is not distributed
- Publishing UI templates requires appropriate admin scope
