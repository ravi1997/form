# API Endpoints

## Health and metrics

- `GET /api/v1/health`
- `GET /api/v1/liveness`
- `GET /api/v1/readiness`
- `GET /api/v1/ready`
- `GET /api/v1/metrics`
- `POST /api/v1/schemas/echo-form`

## Auth

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`
- `POST /api/v1/auth/logout`
- Session and admin routes are provided through the auth blueprint and helper module

## Resources

- `GET/POST/PATCH/DELETE /api/v1/projects`
- `GET/POST/PATCH/DELETE /api/v1/forms`
- `GET/POST/PATCH/DELETE /api/v1/sections`
- `GET/POST/PATCH/DELETE /api/v1/questions`
- `GET/POST/PATCH/DELETE /api/v1/choices`
- `POST /api/v1/actions/...`

## Conditions

- `GET /api/v1/conditions/metadata`
- `GET /api/v1/conditions/operators/metadata`
- `POST /api/v1/conditions/test`
- `POST /api/v1/conditions/test/batch`
- Cache and monitoring endpoints are exposed from the same blueprint

## UI templates

- `GET/POST/PATCH/DELETE /api/v1/ui-templates`

## Rate limits

- `GET/POST/PATCH/DELETE /api/v1/rate-limits`
