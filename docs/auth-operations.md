# Auth Operations Runbook

This document covers operator usage for auth, session, and audit endpoints.

## Prerequisites

- Use an admin access token in the `Authorization: Bearer <token>` header.
- Base URL examples assume `http://localhost:5000`.

## Admin Audit Endpoints

### 1) Generic audit listing

Endpoint: `GET /api/v1/auth/admin/audit-logs`

Supported query parameters:

- `actor_user_uuid`
- `target_user_uuid`
- `session_uuid`
- `action`
- `start_at` (ISO timestamp)
- `end_at` (ISO timestamp)
- `page` (default `1`)
- `page_size` (default `20`, max `100`)
- `cursor` (optional, enables cursor mode)

Examples:

```bash
curl -s "http://localhost:5000/api/v1/auth/admin/audit-logs?page=1&page_size=20" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

```bash
curl -s "http://localhost:5000/api/v1/auth/admin/audit-logs?action=logout&start_at=2026-07-01T00:00:00&page_size=50" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

### 2) User/action/date-range search endpoint

Endpoint: `GET /api/v1/auth/admin/audit-logs/search`

Supported query parameters:

- `user_uuid` (matches actor or target)
- `action`
- `start_at` (ISO timestamp)
- `end_at` (ISO timestamp)
- `page` (default `1`)
- `page_size` (default `20`, max `100`)
- `cursor` (optional, enables cursor mode)

Examples:

```bash
curl -s "http://localhost:5000/api/v1/auth/admin/audit-logs/search?user_uuid=u-123&action=admin_session_revoke&page_size=25" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

```bash
curl -s "http://localhost:5000/api/v1/auth/admin/audit-logs/search?cursor=$CURSOR&page_size=100" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

Compatibility note: legacy `/api/auth/*` paths continue to work via HTTP 308 redirects.

## Cursor Handling

- First request: omit `cursor`, set `page_size`.
- If response has `next_cursor`, pass it in the next request.
- Cursor mode is preferred for very large datasets.
- In cursor mode, `total_items` and `total_pages` may be omitted to avoid expensive count queries.

## Rate-Limit Semantics

Throttled responses return HTTP `429` with:

- `Retry-After` response header (seconds)
- payload `message`
- payload `limit_scope`:
  - `ip` when IP bucket exceeded
  - `user` when user bucket exceeded

Example throttled payload:

```json
{
  "message": "Too many requests for this endpoint. Please try again later.",
  "limit_scope": "user"
}
```

## Query Plan Verification (Mongo)

Collection: `session_audit_logs`

Verify these patterns use indexes:

- user_uuid + created_at: `actor_user_uuid` or `target_user_uuid` with `created_at` sort
- action + created_at
- created_at descending pagination

Run in `mongosh`:

```javascript
db.session_audit_logs.find({ actor_user_uuid: "u-123" })
  .sort({ created_at: -1 })
  .limit(20)
  .explain("executionStats")
```

```javascript
db.session_audit_logs.find({ target_user_uuid: "u-123" })
  .sort({ created_at: -1 })
  .limit(20)
  .explain("executionStats")
```

```javascript
db.session_audit_logs.find({ action: "logout" })
  .sort({ created_at: -1 })
  .limit(20)
  .explain("executionStats")
```

```javascript
db.session_audit_logs.find({ created_at: { $lt: ISODate("2026-07-07T00:00:00Z") } })
  .sort({ created_at: -1 })
  .limit(100)
  .explain("executionStats")
```

What to check:

- `winningPlan` uses `IXSCAN` (not `COLLSCAN`)
- `totalDocsExamined` is close to returned docs for typical queries
- execution time is stable under load
