from __future__ import annotations

import time
import uuid
from datetime import datetime, timedelta
from threading import Lock, Thread
from typing import Any, Dict, Optional

from app.models.condition_management import ConditionAsyncJob
from app.models.form import Condition
from app.services.condition_evaluator import (
    ConditionEvaluationError,
    ConditionEvaluator,
)
from app.services.condition_management_core import ConditionManagementError


class InMemoryConditionQueue:
    """Queue abstraction for async evaluation."""

    def __init__(self):
        self._lock = Lock()

    def enqueue(self, func, *args, **kwargs) -> None:
        thread = Thread(target=func, args=args, kwargs=kwargs, daemon=True)
        thread.start()


_default_queue = InMemoryConditionQueue()


def _run_async_job(job_id: str, retry_count: int = 0) -> None:
    job = ConditionAsyncJob.objects(job_id=job_id).first()
    if not job:
        return
    condition = Condition.objects(uuid=job.condition_uuid).first()
    if not condition:
        job.status = "failed"
        job.error = "Condition not found"
        job.save()
        return

    evaluator = ConditionEvaluator(
        context=job.context,
        enable_tracing=True,
        timeout_ms=job.timeout_ms,
    )
    job.status = "running"
    job.started_at = datetime.utcnow()
    job.save()

    try:
        result = evaluator.evaluate(condition)
        snapshot = evaluator.get_observability_snapshot()
        job.result = bool(result)
        job.trace = snapshot["trace"]
        job.status = "success"
        job.completed_at = datetime.utcnow()
        job.save()
    except ConditionEvaluationError as exc:
        job.error = str(exc)
        if "timeout" in str(exc).lower() and retry_count < job.retries:
            _run_async_job(job_id, retry_count + 1)
            return
        job.status = "timeout" if "timeout" in str(exc).lower() else "failed"
        job.result = bool(job.fallback_result)
        job.completed_at = datetime.utcnow()
        job.save()


def enqueue_async_evaluation(
    condition_uuid: str,
    context: Dict[str, Any],
    *,
    timeout_ms: int = 1000,
    retries: int = 0,
    fallback_result: bool = False,
    queue: Optional[InMemoryConditionQueue] = None,
) -> ConditionAsyncJob:
    condition = Condition.objects(uuid=condition_uuid).first()
    if not condition:
        raise ConditionManagementError("Condition not found")

    job = ConditionAsyncJob(
        job_id=str(uuid.uuid4()),
        condition_uuid=condition_uuid,
        context=context,
        timeout_ms=timeout_ms,
        retries=retries,
        fallback_result=fallback_result,
        status="queued",
    )
    job.save()

    (queue or _default_queue).enqueue(_run_async_job, job.job_id)
    return job


def get_async_job_status(job_id: str) -> Dict[str, Any]:
    job = ConditionAsyncJob.objects(job_id=job_id).first()
    if not job:
        raise ConditionManagementError("Job not found")

    return {
        "job_id": job.job_id,
        "condition_uuid": job.condition_uuid,
        "status": job.status,
        "result": job.result,
        "error": job.error,
        "trace": list(job.trace or []),
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


def evaluate_condition_async(
    condition: Condition,
    context: Dict[str, Any],
    timeout_seconds: float = 2.0,
) -> Dict[str, Any]:
    timeout_ms = max(1, int(timeout_seconds * 1000))
    job = enqueue_async_evaluation(
        condition.uuid,
        context,
        timeout_ms=timeout_ms,
        retries=0,
        fallback_result=False,
    )
    deadline = datetime.utcnow() + timedelta(milliseconds=timeout_ms)
    while datetime.utcnow() < deadline:
        payload = get_async_job_status(job.job_id)
        if payload["status"] in {"success", "failed", "timeout"}:
            return {
                "job_id": payload["job_id"],
                "status": payload["status"],
                "result": payload["result"],
                "trace": payload["trace"],
                "timed_out": payload["status"] == "timeout",
                "error": payload["error"],
            }
        time.sleep(0.02)
    return {
        "job_id": job.job_id,
        "status": "timeout",
        "result": None,
        "trace": [],
        "timed_out": True,
        "error": f"Evaluation timed out after {timeout_seconds}s",
    }
