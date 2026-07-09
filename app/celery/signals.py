from __future__ import annotations

from typing import Any, Dict, Optional

from celery import signals

from app.services.condition_management_async import (
    handle_task_failure,
    handle_task_retry,
    handle_task_success,
)

_REGISTERED = False


def _extract_job_id(args: tuple[Any, ...], kwargs: Dict[str, Any]) -> Optional[str]:
    if args:
        return str(args[0])
    job_id = kwargs.get("job_id")
    return str(job_id) if job_id is not None else None


def register_celery_signals(celery_app, flask_app) -> None:
    global _REGISTERED
    if _REGISTERED:
        return

    @signals.before_task_publish.connect
    def _before_task_publish(sender=None, body=None, headers=None, **_):
        job_id = None
        if isinstance(body, tuple) and body:
            job_id = _extract_job_id(tuple(body[0] or ()), dict(body[1] or {}))
        if job_id is None and headers:
            args = headers.get("argsrepr")
            if isinstance(args, str) and args.startswith("(") and args.endswith(")"):
                # Best-effort fallback; enqueue_async_evaluation already sets queued.
                job_id = None
        return job_id

    @signals.task_prerun.connect
    def _task_prerun(sender=None, task_id=None, task=None, args=None, kwargs=None, **_):
        task_obj = sender or task
        if not task_obj:
            return
        job_id = _extract_job_id(tuple(args or ()), kwargs or {})
        if not job_id and getattr(task_obj, "request", None):
            job_id = _extract_job_id(
                tuple(getattr(task_obj.request, "args", ()) or ()),
                getattr(task_obj.request, "kwargs", {}) or {},
            )
        if job_id:
            from app.services.condition_management_async import _mark_job_status

            _mark_job_status(
                job_id,
                "running",
                celery_task_id=task_id
                or getattr(getattr(task_obj, "request", None), "id", None),
                task_name=getattr(task_obj, "name", None),
            )

    @signals.task_retry.connect
    def _task_retry(sender=None, request=None, reason=None, **_):
        job_id = _extract_job_id(
            tuple(getattr(request, "args", ()) or ()),
            getattr(request, "kwargs", {}) or {},
        )
        if job_id:
            handle_task_retry(
                job_id, getattr(request, "retries", 0), str(reason) if reason else ""
            )

    @signals.task_success.connect
    def _task_success(sender=None, result=None, **kwargs):
        task_obj = sender
        request = getattr(task_obj, "request", None)
        if not request:
            request = kwargs.get("request")
        job_id = _extract_job_id(
            tuple(getattr(request, "args", ()) or ()),
            getattr(request, "kwargs", {}) or {},
        )
        if job_id and isinstance(result, dict):
            handle_task_success(
                job_id, bool(result.get("result")), list(result.get("trace") or [])
            )

    @signals.task_failure.connect
    def _task_failure(
        sender=None, task_id=None, exception=None, args=None, kwargs=None, **_
    ):
        task_obj = sender
        request = getattr(task_obj, "request", None)
        job_id = _extract_job_id(
            tuple(args or getattr(request, "args", ()) or ()),
            kwargs or getattr(request, "kwargs", {}) or {},
        )
        if job_id:
            timeout = exception.__class__.__name__ in {
                "SoftTimeLimitExceeded",
                "TimeLimitExceeded",
            }
            handle_task_failure(
                job_id, str(exception) if exception else "", timeout=timeout
            )

    _REGISTERED = True
