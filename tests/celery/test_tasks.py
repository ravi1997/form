from __future__ import annotations

import pytest
from datetime import timedelta

from app.celery.tasks import process_condition_async_job
from app.models.condition_management import ConditionAsyncJob
from app.models.form import Condition
from app.services import condition_management_async as async_service
from app.services.condition_evaluator import ConditionEvaluationError


def test_task_execution_updates_job_state(app_context, monkeypatch):
    condition = Condition(
        uuid="celery-task-ok",
        conditionType="comparison",
        targetField="status",
        operator="equals",
        operands=["approved"],
        isActive=True,
    ).save()

    monkeypatch.setattr(
        async_service.ConditionEvaluator,
        "evaluate",
        lambda self, condition, *_args, **_kwargs: True,
    )

    job = async_service.enqueue_async_evaluation(
        condition.uuid,
        {"status": "approved"},
        timeout_ms=1000,
        retries=0,
        fallback_result=False,
    )

    updated = ConditionAsyncJob.objects(job_id=job.job_id).first()
    assert updated.status == "success"
    assert updated.result is True
    assert updated.execution_time is not None


def test_task_failure_and_retry_schedule(app_context, monkeypatch):
    condition = Condition(
        uuid="celery-task-retry",
        conditionType="comparison",
        targetField="status",
        operator="equals",
        operands=["approved"],
        isActive=True,
    ).save()

    job = ConditionAsyncJob(
        job_id="celery-retry-job",
        condition_uuid=condition.uuid,
        context={"status": "pending"},
        status="created",
        retries=2,
        timeout_ms=100,
    ).save()

    monkeypatch.setattr(
        async_service.ConditionEvaluator,
        "evaluate",
        lambda self, condition, *_args, **_kwargs: (_ for _ in ()).throw(
            ConditionEvaluationError("retry me")
        ),
    )

    retry_calls = []

    class Request:
        id = "task-1"
        retries = 0

    original_retry = process_condition_async_job.retry

    def fake_retry(*args, **kwargs):
        retry_calls.append((args, kwargs))
        raise RuntimeError("retry-called")

    process_condition_async_job.retry = fake_retry

    with pytest.raises(RuntimeError, match="retry-called"):
        process_condition_async_job.run.__func__(
            type(
                "FakeTask",
                (),
                {
                    "request": Request(),
                    "max_retries": 3,
                    "name": process_condition_async_job.name,
                    "retry": fake_retry,
                },
            )(),
            job.job_id,
        )

    process_condition_async_job.retry = original_retry

    assert retry_calls
    assert retry_calls[0][1]["countdown"] == 10
    updated = ConditionAsyncJob.objects(job_id=job.job_id).first()
    assert updated.status == "retrying"
    assert updated.retry_count == 1


def test_duplicate_execution_protection_skips_second_run(app_context, monkeypatch):
    condition = Condition(
        uuid="celery-dup",
        conditionType="comparison",
        targetField="status",
        operator="equals",
        operands=["approved"],
        isActive=True,
    ).save()

    calls = {"count": 0}

    def evaluate(self, condition, *_args, **_kwargs):
        calls["count"] += 1
        return True

    monkeypatch.setattr(async_service.ConditionEvaluator, "evaluate", evaluate)

    job = ConditionAsyncJob(
        job_id="celery-dup-job",
        condition_uuid=condition.uuid,
        context={"status": "approved"},
        status="created",
        retries=0,
        timeout_ms=1000,
    ).save()

    first = async_service.process_async_job(job.job_id)
    second = async_service.process_async_job(job.job_id)

    assert first["status"] == "success"
    assert second["status"] == "success"
    assert calls["count"] == 1


def test_worker_restart_recovery_reclaims_stale_running_job(app_context, monkeypatch):
    condition = Condition(
        uuid="celery-recover",
        conditionType="comparison",
        targetField="status",
        operator="equals",
        operands=["approved"],
        isActive=True,
    ).save()

    monkeypatch.setattr(
        async_service.ConditionEvaluator,
        "evaluate",
        lambda self, condition, *_args, **_kwargs: True,
    )

    job = ConditionAsyncJob(
        job_id="celery-recover-job",
        condition_uuid=condition.uuid,
        context={"status": "approved"},
        status="running",
        retries=1,
        timeout_ms=1000,
        started_at=async_service._utcnow(),
        lock_token="stale-lock",
        lock_expires_at=async_service._utcnow() - timedelta(seconds=1),
    ).save()

    result = async_service.process_async_job(job.job_id)

    assert result["status"] == "success"
    updated = ConditionAsyncJob.objects(job_id=job.job_id).first()
    assert updated.status == "success"
    assert updated.execution_time is not None
