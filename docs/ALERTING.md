# Alerting

Recommended alert thresholds for the current operational model.

## Authentication

- High auth failure rate: more than 100 failures in 5 minutes
- Refresh token failures: more than 50 failures in 5 minutes
- Invalid token attempts: more than 100 attempts in 5 minutes

## Rate limiting

- Blocked requests: more than 500 blocked requests in 1 minute

## Async jobs

- Queue backlog: more than 1000 queued jobs
- Job failure rate: more than 5% over 10 minutes
- Retry storms: retry count spikes above baseline for 10 minutes
- Worker unavailable: no successful heartbeat for 5 minutes
- Long running tasks: execution time above the configured soft time limit or SLA

## Latency

- p95 request latency above 2 seconds for 5 minutes
- Readiness endpoint failures for 2 consecutive checks

## Database

- MongoDB connection failures in health or readiness checks
- Sustained increase in query latency or ping failure rate
