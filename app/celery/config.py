from __future__ import annotations

from typing import Any, Dict, Mapping

from celery.schedules import crontab

from app.config import BaseConfig


def build_celery_config(config: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "broker_url": BaseConfig.get_str(
            config, "CELERY_BROKER_URL", BaseConfig.CELERY_BROKER_URL
        ),
        "result_backend": BaseConfig.get_str(
            config, "CELERY_RESULT_BACKEND", BaseConfig.CELERY_RESULT_BACKEND
        ),
        "task_default_queue": BaseConfig.get_str(
            config,
            "CELERY_TASK_DEFAULT_QUEUE",
            BaseConfig.CELERY_TASK_DEFAULT_QUEUE,
        ),
        "task_time_limit": BaseConfig.get_int(
            config, "CELERY_TASK_TIME_LIMIT", BaseConfig.CELERY_TASK_TIME_LIMIT
        ),
        "task_soft_time_limit": BaseConfig.get_int(
            config,
            "CELERY_TASK_SOFT_TIME_LIMIT",
            BaseConfig.CELERY_TASK_SOFT_TIME_LIMIT,
        ),
        "task_always_eager": BaseConfig.get_bool(
            config, "CELERY_TASK_ALWAYS_EAGER", BaseConfig.CELERY_TASK_ALWAYS_EAGER
        ),
        "task_eager_propagates": BaseConfig.get_bool(
            config,
            "CELERY_TASK_EAGER_PROPAGATES",
            BaseConfig.CELERY_TASK_EAGER_PROPAGATES,
        ),
        "task_track_started": True,
        "task_acks_late": True,
        "task_reject_on_worker_lost": True,
        "task_acks_on_failure_or_timeout": True,
        "task_default_retry_delay": 10,
        "task_serializer": "json",
        "result_serializer": "json",
        "accept_content": ["json"],
        "result_extended": True,
        "worker_prefetch_multiplier": 1,
        "worker_send_task_events": True,
        "task_send_sent_event": True,
        "timezone": "UTC",
        "enable_utc": True,
        "beat_schedule": {
            "enforce-password-expiry": {
                "task": "app.celery.tasks.enforce_password_expiry_task",
                "schedule": crontab(minute=0, hour="*/6"),
            }
        },
    }


def celery_retry_schedule(retry_count: int) -> int:
    delays = (10, 60, 300)
    if retry_count < 0:
        return delays[0]
    if retry_count >= len(delays):
        return delays[-1]
    return delays[retry_count]
