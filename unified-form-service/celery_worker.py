"""
celery_worker.py
----------------
Celery worker for the unified-form-service.

Handles heavy background tasks:
  - Bulk CSV/PDF exports
  - Batch form submission processing
  - Scheduled analysis runs
  - Webhook delivery retries

Usage:
    # Start worker (from unified-form-service directory)
    celery -A celery_worker.celery worker --loglevel=info

    # Or via Docker Compose dev stack
    docker compose -f docker-compose.dev.yml exec worker celery -A celery_worker.celery worker -l info
"""

import os
from celery import Celery

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery = Celery(
    "unified_form_service",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=[
        "tasks",          # form-builder async tasks (batch submit, exports)
    ]
)

celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    result_expires=3600,             # Results expire after 1 hour
    broker_connection_retry_on_startup=True,
)

# Optional: periodic tasks (beat schedule)
celery.conf.beat_schedule = {
    # Example: Clean up old export files every hour
    "cleanup-exports-hourly": {
        "task": "tasks.cleanup_old_exports",
        "schedule": 3600.0,
    },
}

if __name__ == "__main__":
    celery.start()
