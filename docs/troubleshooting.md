# Troubleshooting

## MongoDB connectivity

- Check `MONGODB_URI`
- Confirm the `mongo` service is healthy in compose
- Use `/api/v1/readiness` to confirm the ping succeeds

## Authentication failures

- Ensure the request uses an access token, not a refresh token
- Confirm the JWT secret and key ID match the issuing environment
- Check the session still exists and is active

## Rate limiting

- Inspect 429 responses for `Retry-After`
- Verify auth and resource rate-limit settings
- In multi-process deployments, ensure Redis is available for distributed limits

## Async jobs

- Check `/api/v1/metrics` for queue state
- Inspect worker logs
- Confirm Celery broker and result backend URLs are set correctly
