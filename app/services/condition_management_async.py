from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional, Tuple

from celery import current_app as celery_current_app
from celery.result import AsyncResult
from celery.exceptions import SoftTimeLimitExceeded, TimeLimitExceeded
from mongoengine.queryset.visitor import Q

from app.models.condition_management import ConditionAsyncJob
from app.models.form import Condition
from app.services.condition_evaluator import (
    ConditionEvaluationError,
    ConditionEvaluator,
)
from app.services.condition_management_core import ConditionManagementError

_JOB_LOCK_TTL_SECONDS = 10 * 60


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _is_retryable_error(exc: Exception) -> bool:
    return isinstance(
        exc, (ConditionEvaluationError, SoftTimeLimitExceeded, TimeLimitExceeded)
    )


def _serialize_exception(exc: Exception) -> str:
    return str(exc) or exc.__class__.__name__


def _task_identity(task: Any = None) -> Tuple[Optional[str], Optional[str]]:
    if task is None:
        return None, None
    request = getattr(task, "request", None)
    if request is None:
        return None, getattr(task, "name", None)
    return getattr(request, "id", None), getattr(task, "name", None)


def _mark_job_status(
    job_id: str,
    status: str,
    *,
    celery_task_id: Optional[str] = None,
    task_name: Optional[str] = None,
    retry_count: Optional[int] = None,
    error_message: Optional[str] = None,
    result: Optional[bool] = None,
    started_at: Optional[datetime] = None,
    completed_at: Optional[datetime] = None,
    execution_time: Optional[float] = None,
    lock_token: Optional[str] = None,
    lock_expires_at: Optional[datetime] = None,
    trace: Optional[list[Dict[str, Any]]] = None,
) -> Optional[ConditionAsyncJob]:
    updates: Dict[str, Any] = {"status": status}
    if celery_task_id is not None:
        updates["celery_task_id"] = celery_task_id
    if task_name is not None:
        updates["task_name"] = task_name
    if retry_count is not None:
        updates["retry_count"] = retry_count
    if error_message is not None:
        updates["error_message"] = error_message
    if result is not None:
        updates["result"] = result
    if started_at is not None:
        updates["started_at"] = started_at
    if completed_at is not None:
        updates["completed_at"] = completed_at
    if execution_time is not None:
        updates["execution_time"] = execution_time
    if lock_token is not None:
        updates["lock_token"] = lock_token
    if lock_expires_at is not None:
        updates["lock_expires_at"] = lock_expires_at
    if trace is not None:
        updates["trace"] = trace
    updates["updated_at"] = _utcnow()
    return ConditionAsyncJob.objects(job_id=job_id).modify(
        new=True,
        set__status=status,
        **{f"set__{key}": value for key, value in updates.items() if key != "status"},
    )


def _claim_job(
    job_id: str,
    *,
    celery_task_id: Optional[str] = None,
    task_name: Optional[str] = None,
) -> Optional[ConditionAsyncJob]:
    now = _utcnow()
    lock_token = str(uuid.uuid4())
    lock_expires_at = now + timedelta(seconds=_JOB_LOCK_TTL_SECONDS)
    claim_filter = Q(status__in=["created", "queued", "retrying"]) | (
        Q(status="running")
        & (Q(lock_expires_at__exists=False) | Q(lock_expires_at__lte=now))
    )
    job = ConditionAsyncJob.objects(job_id=job_id)
    job = job.filter(claim_filter).modify(
        new=True,
        set__status="running",
        set__started_at=now,
        set__celery_task_id=celery_task_id,
        set__task_name=task_name,
        set__lock_token=lock_token,
        set__lock_expires_at=lock_expires_at,
        set__updated_at=now,
        inc__retry_count=1,
    )
    if job:
        job.lock_token = lock_token
        job.lock_expires_at = lock_expires_at
    return job


def create_async_job(
    condition_uuid: str,
    context: Dict[str, Any],
    *,
    timeout_ms: int = 1000,
    retries: int = 0,
    fallback_result: bool = False,
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
        status="created",
    )
    job.save()
    return job


def enqueue_async_evaluation(
    condition_uuid: str,
    context: Dict[str, Any],
    *,
    timeout_ms: int = 1000,
    retries: int = 0,
    fallback_result: bool = False,
    queue: Optional[Any] = None,
) -> ConditionAsyncJob:
    job = create_async_job(
        condition_uuid,
        context,
        timeout_ms=timeout_ms,
        retries=retries,
        fallback_result=fallback_result,
    )
    _mark_job_status(job.job_id, "queued")
    from app.celery.tasks import process_condition_async_job

    apply_kwargs = {"args": [job.job_id]}
    if queue:
        apply_kwargs["queue"] = queue
    task_result = process_condition_async_job.apply_async(**apply_kwargs)
    ConditionAsyncJob.objects(job_id=job.job_id).update_one(
        set__celery_task_id=task_result.id,
        set__task_name=process_condition_async_job.name,
        set__updated_at=_utcnow(),
    )
    job.reload()
    return job


def process_async_job(job_id: str, *, task: Any = None) -> Dict[str, Any]:
    job = ConditionAsyncJob.objects(job_id=job_id).first()
    if not job:
        raise ConditionManagementError("Job not found")

    task_id, task_name = _task_identity(task)
    claimed = _claim_job(job_id, celery_task_id=task_id, task_name=task_name)
    if not claimed:
        current = ConditionAsyncJob.objects(job_id=job_id).first()
        if not current:
            raise ConditionManagementError("Job not found")
        return {
            "job_id": current.job_id,
            "status": current.status,
            "result": current.result,
            "error": current.error,
            "trace": list(current.trace or []),
        }

    condition = Condition.objects(uuid=claimed.condition_uuid).first()
    if not condition:
        _mark_job_status(
            job_id,
            "failed",
            error_message="Condition not found",
            completed_at=_utcnow(),
        )
        raise ConditionManagementError("Condition not found")

    evaluator = ConditionEvaluator(
        context=claimed.context,
        enable_tracing=True,
        timeout_ms=claimed.timeout_ms,
    )
    started_at = _ensure_aware(claimed.started_at) or _utcnow()
    try:
        result = evaluator.evaluate(condition)
        snapshot = evaluator.get_observability_snapshot()
        completed_at = _utcnow()
        execution_time = max(0.0, (completed_at - started_at).total_seconds() * 1000)
        _mark_job_status(
            job_id,
            "success",
            result=bool(result),
            trace=snapshot["trace"],
            completed_at=completed_at,
            execution_time=execution_time,
        )
        return {
            "job_id": job_id,
            "status": "success",
            "result": bool(result),
            "trace": snapshot["trace"],
            "error": None,
        }
    except Exception as exc:
        error_message = _serialize_exception(exc)
        retry_count = claimed.retry_count or 0
        completed_at = _utcnow()
        execution_time = max(0.0, (completed_at - started_at).total_seconds() * 1000)
        if _is_retryable_error(exc) and retry_count < claimed.retries:
            _mark_job_status(
                job_id,
                "retrying",
                error_message=error_message,
                completed_at=completed_at,
                execution_time=execution_time,
            )
            raise

        final_status = (
            "timeout"
            if isinstance(exc, (SoftTimeLimitExceeded, TimeLimitExceeded))
            or "timeout" in error_message.lower()
            else "failed"
        )
        _mark_job_status(
            job_id,
            final_status,
            error_message=error_message,
            result=bool(claimed.fallback_result),
            completed_at=completed_at,
            execution_time=execution_time,
        )
        if final_status == "timeout":
            raise ConditionEvaluationError(error_message) from exc
        raise ConditionEvaluationError(error_message) from exc


def handle_task_retry(job_id: str, retry_count: int, error_message: str) -> None:
    _mark_job_status(
        job_id,
        "retrying",
        retry_count=retry_count,
        error_message=error_message,
    )


def handle_task_failure(
    job_id: str, error_message: str, *, timeout: bool = False
) -> None:
    status = "timeout" if timeout else "failed"
    _mark_job_status(job_id, status, error_message=error_message)


def handle_task_success(job_id: str, result: bool, trace: list[Dict[str, Any]]) -> None:
    _mark_job_status(job_id, "success", result=result, trace=trace)


def get_async_queue_status() -> Dict[str, Any]:
    queued = ConditionAsyncJob.objects(status="queued").count()
    running = ConditionAsyncJob.objects(status="running").count()
    retrying = ConditionAsyncJob.objects(status="retrying").count()
    failed = ConditionAsyncJob.objects(status="failed").count()
    success = ConditionAsyncJob.objects(status="success").count()
    timeout = ConditionAsyncJob.objects(status="timeout").count()
    cancelled = ConditionAsyncJob.objects(status="cancelled").count()

    celery_status: Dict[str, Any] = {
        "active": None,
        "reserved": None,
        "scheduled": None,
        "workers": None,
    }
    try:
        inspector = celery_current_app.control.inspect(timeout=1.0)
        celery_status["active"] = inspector.active() or {}
        celery_status["reserved"] = inspector.reserved() or {}
        celery_status["scheduled"] = inspector.scheduled() or {}
        celery_status["workers"] = inspector.ping() or {}
    except Exception:
        celery_status["workers"] = None

    return {
        "created": ConditionAsyncJob.objects(status="created").count(),
        "queued": queued,
        "running": running,
        "retrying": retrying,
        "success": success,
        "failed": failed,
        "timeout": timeout,
        "cancelled": cancelled,
        "oldest_queued_at": (
            ConditionAsyncJob.objects(status="queued")
            .order_by("created_at")
            .first()
            .created_at.isoformat()
            if queued
            else None
        ),
        "oldest_running_at": (
            ConditionAsyncJob.objects(status="running")
            .order_by("created_at")
            .first()
            .created_at.isoformat()
            if running
            else None
        ),
        "worker_available": bool(celery_status["workers"]),
        "celery": celery_status,
    }


def get_async_job_status(job_id: str) -> Dict[str, Any]:
    job = ConditionAsyncJob.objects(job_id=job_id).first()
    if not job:
        raise ConditionManagementError("Job not found")

    return {
        "job_id": job.job_id,
        "condition_uuid": job.condition_uuid,
        "status": job.status,
        "celery_task_id": job.celery_task_id,
        "task_name": job.task_name,
        "result": job.result,
        "error": job.error,
        "retry_count": job.retry_count,
        "retries": job.retries,
        "execution_time": job.execution_time,
        "trace": list(job.trace or []),
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
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
    result = AsyncResult(job.celery_task_id)
    try:
        payload = result.get(timeout=timeout_seconds, propagate=False)
    except Exception:
        payload = None

    if isinstance(payload, dict):
        status = str(payload.get("status") or "failed")
        return {
            "job_id": payload.get("job_id", job.job_id),
            "status": status,
            "result": payload.get("result"),
            "trace": payload.get("trace", []),
            "timed_out": status == "timeout",
            "error": payload.get("error"),
        }

    payload = get_async_job_status(job.job_id)
    if payload["status"] in {"success", "failed", "timeout", "cancelled"}:
        return {
            "job_id": payload["job_id"],
            "status": payload["status"],
            "result": payload["result"],
            "trace": payload["trace"],
            "timed_out": payload["status"] == "timeout",
            "error": payload["error"],
        }
    return {
        "job_id": job.job_id,
        "status": "timeout",
        "result": None,
        "trace": [],
        "timed_out": True,
        "error": f"Evaluation timed out after {timeout_seconds}s",
    }
