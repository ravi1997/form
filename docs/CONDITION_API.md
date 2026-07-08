# Condition API Guide

Base path: `/api/v1/conditions`

## Discovery & Metadata
- `GET /metadata`
- `GET /operators/metadata`

## Testing
- `POST /test`
- `POST /test/batch`

## Cache
- `GET /cache/metrics`
- `POST /cache/invalidate/<condition_uuid>`

## Usage & Monitoring
- `GET /usage/<condition_uuid>`
- `POST /impact/<condition_uuid>`
- `GET /monitoring/graph`
- `GET /monitoring/heatmap`
- `GET /monitoring/unused`
- `GET /monitoring/most-used`
- `GET /monitoring/evaluation-stats`

## Presets
- `POST /presets`
- `GET /presets`
- `POST /presets/import`
- `GET /presets/export`

## Approval & Versioning
- `POST /<condition_uuid>/approval/transition`
- `POST /<condition_uuid>/approval/rollback`
- `GET /<condition_uuid>/versions`
- `POST /<condition_uuid>/versions/record`
- `POST /<condition_uuid>/versions/restore`

## Bulk
- `POST /bulk/create`
- `PATCH /bulk/update`
- `DELETE /bulk/delete`
- `POST /bulk/validate`
- `POST /bulk/test`
- `POST /bulk/import`
- `GET /bulk/export`

## Async
- `POST /async/evaluate`
- `GET /async/<job_id>`
