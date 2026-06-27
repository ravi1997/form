# Release Notes

## Form Response Service

This release finalizes a backend-only response service for form data.

### Stable contract

- `POST /forms/ingest`
- `GET /forms/<form_id>`
- `POST /forms/<form_id>/responses`
- `GET /forms/<form_id>/responses`
- `GET /responses/<response_id>`
- `PATCH /responses/<response_id>`
- `POST /sync/analyser`
- `GET /healthz`

### Core implementation

- SQLite-backed persistence with explicit schema bootstrap
- small repository interface for future storage adapters
- isolated analyser sync payload transformation
- readiness endpoint for deployment checks

### What is intentionally out of scope

- form authoring
- branching, merge, publish, or version management
- auth/ACL
- workflows, receipts, uploads, exports, or tenant isolation
- frontend UI

### Verification

The test suite covers ingestion, validation, response lifecycle, persistence bootstrap,
health checks, and analyser sync payload generation.

