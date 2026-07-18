from __future__ import annotations

from datetime import datetime, timezone
from app.celery.app import celery_app
from app.celery.config import celery_retry_schedule
from app.models.condition_management import ConditionAsyncJob
from app.services.condition_management_async import (
    ConditionEvaluationError,
    process_async_job,
)
from app.services.password_policy import enforce_password_expiry


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


@celery_app.task(
    bind=True,
    name="app.celery.tasks.enforce_password_expiry_task",
    acks_late=False,
)
def enforce_password_expiry_task(self):
    return {"updated_count": enforce_password_expiry()}


@celery_app.task(
    bind=True,
    name="app.celery.tasks.trigger_response_webhook_task",
    acks_late=True,
    max_retries=3,
)
def trigger_response_webhook_task(self, response_uuid: str, event_type: str):
    """Asynchronously process response submissions, reviews, or approvals to trigger integrations."""
    from app.models.form import FormResponse

    response = FormResponse.objects(uuid=response_uuid).first()
    if not response:
        return {"status": "ignored", "reason": "response_not_found"}

    # Simulate executing integrations or webhook HTTP POST triggers.
    # In production, this can perform requests.post to configured webhook URL endpoints.
    return {
        "status": "success",
        "response_uuid": response_uuid,
        "event_type": event_type,
        "triggered_at": datetime.now(timezone.utc).isoformat(),
    }
