# Observability

The service exposes structured logging, request metrics, security event logs, and async queue visibility.

## Request metrics

`GET /api/v1/metrics` returns:

- request totals
- inflight request count
- average request latency
- response counts by status code
- async queue snapshot:
  - queued
  - running
  - failed
  - timeout

## Structured logging

Logs are emitted as JSON and include:

- request id
- correlation id
- method and path
- user id when available
- resource and operation context
- failure reason or exception details where relevant

## Async visibility

Async condition jobs are stored in MongoDB and recovered on application startup. Queue visibility is exposed through the metrics endpoint and the async job status endpoint.
