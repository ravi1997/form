# Docs vs Code Gap Report

Scope:
- `app/`
- `docs/`
- route surface exposed under `/api/v1`

Status:
- The password-change policy feature is documented.
- The route catalog is now much closer to code, but this is still not a literal 1:1 copy of the OpenAPI surface.

## Classified Findings

### Already documented

- `POST /api/v1/auth/change-password`
- `must_change_password` user flag
- admin single-user and bulk password flagging
- password-expiry policy service
- Celery beat task for password-expiry enforcement
- `MAX_PASSWORD_EXPIRE_DAYS`

### Documented but coarse

- Resources API coverage in [`docs/api/overview.md`](../api/overview.md)
- Conditions API coverage in [`docs/api/overview.md`](../api/overview.md)
- Authentication/admin overview in [`docs/api/authentication.md`](../api/authentication.md)

These pages now name the major route families, but they intentionally do not enumerate every nested subroute, path parameter, or response shape.

### Still undocumented in prose docs

- Route-level request/response details for:
  - organization invitation acceptance
  - organization admin management
  - nested section/question/choice/action routes
  - form response history and action-execution history
  - the full condition-management route set
- Exact auth-admin user lifecycle operations beyond sessions and password flagging
- Explicit mention of the public form-response submission route in the auth overview

### Docs that could drift later

- [`docs/api/endpoints.md`](../api/endpoints.md)
- [`docs/api/overview.md`](../api/overview.md)
- [`docs/architecture.md`](../architecture.md)
- [`docs/testing.md`](../testing.md)

These should be refreshed if the OpenAPI surface changes materially.

## Code Evidence

- Route registration starts in [`app/api/__init__.py`](../../app/api/__init__.py)
- App bootstrap occurs in [`app/openapi.py`](../../app/openapi.py)
- Authentication routes are in [`app/api/auth.py`](../../app/api/auth.py)
- Admin auth routes are in [`app/api/auth_admin_routes.py`](../../app/api/auth_admin_routes.py)
- Organization routes are in [`app/api/resources_organizations.py`](../../app/api/resources_organizations.py)
- Form routes are in [`app/api/resources_forms.py`](../../app/api/resources_forms.py)
- Section routes are in [`app/api/resources_sections.py`](../../app/api/resources_sections.py)
- Question routes are in [`app/api/resources_questions.py`](../../app/api/resources_questions.py)
- Choice routes are in [`app/api/resources_choices.py`](../../app/api/resources_choices.py)
- Action routes are in [`app/api/resources_actions.py`](../../app/api/resources_actions.py)
- Condition routes are in [`app/api/conditions.py`](../../app/api/conditions.py)
- Password policy service is in [`app/services/password_policy.py`](../../app/services/password_policy.py)
- Celery schedule and task are in [`app/celery/config.py`](../../app/celery/config.py) and [`app/celery/tasks.py`](../../app/celery/tasks.py)

## Bottom Line

The docs now cover the new password policy feature and the major API families. The remaining gap is mostly granularity, not missing feature families.
