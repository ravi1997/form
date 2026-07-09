from __future__ import annotations

from app.celery.app import celery_app
from app.celery.config import celery_retry_schedule
from app.models.condition_management import ConditionAsyncJob
from app.services.condition_management_async import (
    ConditionEvaluationError,
    process_async_job,
)


@celery_app.task(
    bind=True,
    name="app.celery.tasks.process_condition_async_job",
    acks_late=True,
    reject_on_worker_lost=True,
    max_retries=3,
)
def process_condition_async_job(self, job_id: str):
    try:
        return process_async_job(job_id, task=self)
    except ConditionEvaluationError as exc:
        job = ConditionAsyncJob.objects(job_id=job_id).first()
        max_job_retries = job.retries if job else 0
        delay = celery_retry_schedule(self.request.retries)
        if self.request.retries >= min(self.max_retries, max_job_retries):
            raise
        raise self.retry(exc=exc, countdown=delay)
