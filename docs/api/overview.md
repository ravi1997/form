# API Overview

The API is served under `/api/v1` and uses `flask-openapi3` for request and response schema registration.

## Canonical References

- [`docs/api/endpoints.md`](./endpoints.md) is the route-by-route reference with path parameters, request bodies, and response schema names.
- [`docs/api/authentication.md`](./authentication.md) describes authentication flow, token handling, and access rules.
- [`docs/architecture.md`](../architecture.md) describes the service boundaries and runtime layout.

## Route Groups

| Group | Base paths |
| --- | --- |
| System | `/api/v1/health`, `/api/v1/liveness`, `/api/v1/readiness`, `/api/v1/ready`, `/api/v1/metrics`, `/api/v1/schemas/echo-form` |
| Auth | `/api/v1/auth/...` including user session, password-change, admin user, audit, and config-health routes |
| Organizations | `/api/v1/organizations/...` and `/api/v1/invitations/<uuid>/accept` |
| Resources | `/api/v1/projects/...` including forms, sections, questions, choices, actions, workflow, responses, and effective UI config |
| Conditions | `/api/v1/conditions/...` including metadata, testing, cache, monitoring, presets, approval, versioning, bulk, and async routes |
| UI templates | `/api/v1/ui/theme-templates...` and `/api/v1/ui/layout-templates...` |
| Rate limits | `/api/v1/admin/rate-limits/...` |

## Authentication Conventions

- Protected routes use `Authorization: Bearer <access token>`.
- Admin routes enforce privilege checks before touching user or resource state.
- Resource routes also apply RBAC and rate-limit middleware where appropriate.

## Compatibility

Legacy `/api/...` routes remain documented only where compatibility is still active; the canonical surface is `/api/v1`.

