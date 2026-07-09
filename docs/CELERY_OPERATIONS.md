# Celery Operations

This service uses Celery for async condition evaluation.
Redis is the broker and result backend. MongoDB remains the source of truth for
job metadata, status history, retry counts, timestamps, and audit state.

## Start workers

```bash
celery -A app.celery.worker worker --loglevel=info
```

For periodic tasks:

```bash
celery -A app.celery.worker beat --loglevel=info
```

## Scale workers

- Increase worker replicas horizontally when async queue depth grows.
- Keep `CELERY_TASK_ACKS_LATE=True` and `reject_on_worker_lost=True` enabled so
  tasks are re-delivered if a worker exits mid-task.
- Use separate API and worker deployment units so worker scale does not affect
  request latency.

## Retry behavior

- Retries are bounded by the job record and Celery's max retries.
- Retry delays are exponential by job attempt: 10s, 60s, then 300s for later
  retries.
- Job status transitions through `created -> queued -> running -> retrying ->
  success|failed|timeout|cancelled`.

## Troubleshooting

- If jobs are not moving, check:
  - Redis availability
  - Celery worker logs
  - MongoDB connectivity
  - `GET /api/v1/metrics` for queue depth and worker availability
- If a job is stuck in `running`, confirm whether the worker died mid-task.
  The MongoDB record keeps the last known state and timestamps, which makes the
  job observable even after restart.
- If tasks time out, verify `CELERY_TASK_SOFT_TIME_LIMIT` and
  `CELERY_TASK_TIME_LIMIT` are set appropriately for the workload.

## Compatibility notes

- The async job collection is preserved; existing records remain valid.
- MongoDB continues to store the lifecycle history even though Celery performs
  execution and retry orchestration.
- The API still exposes job status through the existing condition management
  endpoints.
