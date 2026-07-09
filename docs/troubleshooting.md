# Troubleshooting

## MongoDB connectivity

- Check `MONGODB_URI`
- Confirm the `mongo` service is healthy in compose
- Use `/api/v1/readiness` to confirm the ping succeeds
- If readiness returns degraded, check network reachability and auth credentials

## Authentication failures

- Ensure the request uses an access token, not a refresh token
- Confirm the JWT secret and key ID match the issuing environment
- Check the session still exists and is active
- If refresh fails, confirm the token is not revoked and the user still exists

## Rate limiting

- Inspect 429 responses for `Retry-After`
- Verify auth and resource rate-limit settings
- In multi-process deployments, ensure Redis is available for distributed limits
- If Redis is down and `RATE_LIMIT_FAIL_OPEN=false`, the endpoint should fail instead of returning a fallback 503

## Async jobs

- Check `/api/v1/metrics` for queue state
- Inspect worker logs
- Confirm Celery broker and result backend URLs are set correctly
- Verify the job record in `condition_async_jobs` if a task appears stuck

## Logging

- Increase `LOG_LEVEL` to `DEBUG` temporarily when tracing auth or RBAC issues
- Check the rotating logs in `LOG_DIR`
- Look for the request ID in logs to correlate related events

## UI template issues

- Confirm the template has a current revision UUID
- Ensure the publishing actor is super-admin or one of the template admins
- Verify the template revision itself is marked published before publishing the template
