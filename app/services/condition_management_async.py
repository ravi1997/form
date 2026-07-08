from __future__ import annotations

import time
import uuid
import atexit
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from threading import Lock
from typing import Any, Dict, Optional

from app.models.condition_management import ConditionAsyncJob
from app.models.form import Condition
from app.services.condition_evaluator import (
    ConditionEvaluationError,
    ConditionEvaluator,
)
from app.services.condition_management_core import ConditionManagementError

# Maximum concurrent async evaluation workers. Unbounded thread creation is a
# denial-of-service risk; this cap prevents thread exhaustion under load.
_MAX_ASYNC_WORKERS = 8


class InMemoryConditionQueue:
    """Queue abstraction for async evaluation backed by a bounded thread pool."""

    def __init__(self, max_workers: int = _MAX_ASYNC_WORKERS):
        self._lock = Lock()
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="cond-eval"
        )

    def enqueue(self, func, *args, **kwargs) -> None:
        self._executor.submit(func, *args, **kwargs)

    def close(self, wait: bool = True) -> None:
        self._executor.shutdown(wait=wait, cancel_futures=not wait)


_default_queue = InMemoryConditionQueue()
atexit.register(_default_queue.close)


def recover_pending_async_jobs(
    queue: Optional[InMemoryConditionQueue] = None,
) -> Dict[str, int]:
    """Requeue pending async jobs after a worker or process restart.

    The queue itself is still in-memory, but the authoritative job state lives
    in MongoDB. On startup we can recover jobs that were queued or running when
    the previous process exited and make them visible again.
    """
    pending_queue = queue or _default_queue
    stats = {"requeued": 0, "running_reset": 0}

    for job in ConditionAsyncJob.objects(status__in=("queued", "running")):
        if job.status == "running":
            job.status = "queued"
            job.started_at = None
            job.save()
            stats["running_reset"] += 1
        pending_queue.enqueue(_run_async_job, job.job_id, 0, queue)
        stats["requeued"] += 1

    return stats


def _run_async_job(
    job_id: str,
    retry_count: int = 0,
    queue: Optional[InMemoryConditionQueue] = None,
) -> None:
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
    job.started_at = datetime.now(timezone.utc)
    job.save()

    try:
        result = evaluator.evaluate(condition)
        snapshot = evaluator.get_observability_snapshot()
        job.result = bool(result)
        job.trace = snapshot["trace"]
        job.status = "success"
        job.completed_at = datetime.now(timezone.utc)
        job.save()
    except ConditionEvaluationError as exc:
        job.error = str(exc)
        if "timeout" in str(exc).lower() and retry_count < job.retries:
            (queue or _default_queue).enqueue(
                _run_async_job, job_id, retry_count + 1, queue
            )
            return
        job.status = "timeout" if "timeout" in str(exc).lower() else "failed"
        job.result = bool(job.fallback_result)
        job.completed_at = datetime.now(timezone.utc)
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

    (queue or _default_queue).enqueue(_run_async_job, job.job_id, 0, queue)
    return job


def get_async_queue_status() -> Dict[str, Any]:
    """Return a coarse queue snapshot for observability and health endpoints."""
    queued_jobs = ConditionAsyncJob.objects(status="queued").order_by("created_at")
    running_jobs = ConditionAsyncJob.objects(status="running").order_by("created_at")
    oldest_queued = queued_jobs.first()
    oldest_running = running_jobs.first()
    return {
        "queued": queued_jobs.count(),
        "running": running_jobs.count(),
        "failed": ConditionAsyncJob.objects(status="failed").count(),
        "timeout": ConditionAsyncJob.objects(status="timeout").count(),
        "oldest_queued_at": (
            oldest_queued.created_at.isoformat()
            if oldest_queued and oldest_queued.created_at
            else None
        ),
        "oldest_running_at": (
            oldest_running.created_at.isoformat()
            if oldest_running and oldest_running.created_at
            else None
        ),
    }


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
    deadline = datetime.now(timezone.utc) + timedelta(milliseconds=timeout_ms)
    while datetime.now(timezone.utc) < deadline:
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
