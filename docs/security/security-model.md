# Security Model

## Authentication

- JWT access and refresh tokens are signed with HS256
- Refresh tokens are tied to MongoDB session records
- Refresh token rotation is supported

## Authorization

- Resource access is controlled with RBAC
- Roles are stored per organization
- Resource route permissions are enforced in the resources API helper layer

## Hardening

- Security and request headers are set by middleware
- Sensitive values are masked in rotating logs
- `CORS_ALLOW_ORIGINS` must be restricted in browser-facing deployments
