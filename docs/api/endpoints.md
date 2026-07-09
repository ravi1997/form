# API Endpoints

## Health and metrics

- `GET /api/v1/health` returns `ok`
- `GET /api/v1/liveness` returns `alive`
- `GET /api/v1/readiness` pings MongoDB and returns `ready` or `degraded`
- `GET /api/v1/ready` aliases readiness
- `GET /api/v1/metrics` returns request metrics plus async queue status
- `POST /api/v1/schemas/echo-form` validates a form schema body and echoes it back

## Auth

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`
- `POST /api/v1/auth/logout`
- `GET /api/v1/auth/me`
- `GET /api/v1/auth/sessions`
- `POST /api/v1/auth/sessions/revoke`
- `POST /api/v1/auth/logout-all`
- `GET /api/v1/auth/admin/users/<user_uuid>/sessions`
- `POST /api/v1/auth/admin/users/<user_uuid>/sessions/revoke`
- `POST /api/v1/auth/admin/users/<user_uuid>/sessions/revoke-all`
- `GET /api/v1/auth/admin/audit-logs`
- `GET /api/v1/auth/admin/config-health`

## Resources

- `POST /api/v1/projects`
- `GET /api/v1/projects`
- `GET /api/v1/projects/<project_uuid>`
- `PATCH /api/v1/projects/<project_uuid>`
- `DELETE /api/v1/projects/<project_uuid>`
- `POST /api/v1/projects/<project_uuid>/versions`
- `PATCH /api/v1/projects/<project_uuid>/versions/<version_uuid>`
- `POST /api/v1/projects/<project_uuid>/forms`
- `GET /api/v1/projects/<project_uuid>/forms`
- `GET /api/v1/projects/<project_uuid>/forms/<form_uuid>`
- `PATCH /api/v1/projects/<project_uuid>/forms/<form_uuid>`
- `DELETE /api/v1/projects/<project_uuid>/forms/<form_uuid>`
- `POST /api/v1/projects/<project_uuid>/forms/<form_uuid>/versions`
- `POST /api/v1/projects/<project_uuid>/forms/<form_uuid>/workflow/...`
- `GET /api/v1/projects/<project_uuid>/forms/<form_uuid>/ui/effective`
- Sections, questions, choices, and actions follow the same project/form nesting

## Conditions

- `GET /api/v1/conditions/metadata`
- `GET /api/v1/conditions/operators/metadata`
- `POST /api/v1/conditions/test`
- `POST /api/v1/conditions/test/batch`
- `GET /api/v1/conditions/cache/metrics`
- `POST /api/v1/conditions/cache/invalidate/<condition_uuid>`
- `GET /api/v1/conditions/usage/<condition_uuid>`
- `POST /api/v1/conditions/impact/<condition_uuid>`
- `GET /api/v1/conditions/monitoring/graph`
- `GET /api/v1/conditions/monitoring/heatmap`
- `GET /api/v1/conditions/monitoring/unused`
- `GET /api/v1/conditions/monitoring/most-used`
- `GET /api/v1/conditions/monitoring/evaluation-stats`
- `POST /api/v1/conditions/presets`
- `GET /api/v1/conditions/presets`
- `POST /api/v1/conditions/presets/import`
- `GET /api/v1/conditions/presets/export`
- `POST /api/v1/conditions/<condition_uuid>/approval/transition`
- `POST /api/v1/conditions/<condition_uuid>/approval/rollback`
- `GET /api/v1/conditions/<condition_uuid>/versions`
- `POST /api/v1/conditions/<condition_uuid>/versions/record`
- `POST /api/v1/conditions/<condition_uuid>/versions/restore`
- `POST /api/v1/conditions/bulk/create`
- `PATCH /api/v1/conditions/bulk/update`
- `DELETE /api/v1/conditions/bulk/delete`
- `POST /api/v1/conditions/bulk/validate`
- `POST /api/v1/conditions/bulk/test`
- `POST /api/v1/conditions/bulk/import`
- `GET /api/v1/conditions/bulk/export`
- `POST /api/v1/conditions/async/evaluate`
- `GET /api/v1/conditions/async/<job_id>`

## UI templates

- `POST /api/v1/ui/theme-templates`
- `POST /api/v1/ui/theme-templates/<template_uuid>/revisions/<revision_uuid>/publish`
- `POST /api/v1/ui/layout-templates`
- `POST /api/v1/ui/layout-templates/<template_uuid>/revisions/<revision_uuid>/publish`

## Rate limits

- `POST /api/v1/admin/rate-limits/configs`
- `GET /api/v1/admin/rate-limits/configs`
- `GET /api/v1/admin/rate-limits/configs/<rule_id>`
- `PATCH /api/v1/admin/rate-limits/configs/<rule_id>`
- `POST /api/v1/admin/rate-limits/configs/<rule_id>/reset`
- `DELETE /api/v1/admin/rate-limits/configs/<rule_id>`
- `POST /api/v1/admin/rate-limits/bulk/update`
- `POST /api/v1/admin/rate-limits/bulk/reset`
- `GET /api/v1/admin/rate-limits/logs`
- `GET /api/v1/admin/rate-limits/status`
