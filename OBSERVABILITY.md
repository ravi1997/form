# Observability

The service exposes structured logging, request metrics, security event logs, Celery worker visibility, and MongoDB-backed async job history.

## Request metrics

`GET /api/v1/metrics` returns:

- request totals
- inflight request count
- average request latency
- response counts by status code
- Celery queue health:
  - pending tasks
  - active tasks
  - worker availability
- async queue snapshot:
  - queued
  - running
  - retrying
  - failed
  - timeout
  - success
  - cancelled
  - worker availability
  - Celery inspector snapshot when a broker is reachable

## Structured logging

Logs are emitted as JSON and include:

- request id
- correlation id
- method and path
- user id when available
- resource and operation context
- failure reason or exception details where relevant

## Async visibility

Async condition jobs are executed by Celery workers, while MongoDB stores the canonical job ledger:

- job id
- Celery task id
- task name
- status
- retry count
- timestamps
- error message
- execution time

Queue visibility is exposed through the metrics endpoint, the async job status endpoint, and Celery worker logs/inspect output. Jobs remain durable across worker restarts because the metadata is stored in MongoDB and execution is distributed via Redis.

## Monitoring retention

Condition evaluation statistics are retained for the window configured by
`MONITORING_STATS_RETENTION_DAYS` (default: 30 days). See
[docs/MONITORING_DATA_RETENTION.md](docs/MONITORING_DATA_RETENTION.md) for the
retention strategy and verification steps.

## Dashboards

Grafana dashboard definitions live in `dashboards/`:

- `application.json`
- `async_jobs.json`
- `security.json`
