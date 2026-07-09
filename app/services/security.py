"""MongoDB-backed security helpers.

Provides:
- ``check_and_increment_rate_limit``: atomic upsert counter for auth endpoint
  rate limiting.  Uses naive UTC internally so comparisons work against
  MongoEngine DateTimeField values (which strip tzinfo on retrieval).
- ``log_session_audit_event``: persists auth audit events to session_audit_logs
  with TTL-based retention.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from flask import current_app
from mongoengine.errors import NotUniqueError, OperationError, ValidationError

from app.config import BaseConfig
from app.models.auth import RateLimitCounter, SessionAuditLog
from app.services import get_rotating_logger
from app.utils import utcnow

logger = get_rotating_logger()

def check_and_increment_rate_limit(
    *,
    scope: str,
    key: str,
    max_requests: int,
    window_seconds: int,
) -> Dict[str, int | bool]:
    logger.log_debug(
        "rate_limit_check_started",
        context={
            "scope": scope,
            "key": key,
            "max_requests": max_requests,
            "window_seconds": window_seconds,
        },
    )
    now = utcnow()
    bucket_epoch = int(now.timestamp()) // window_seconds
    expires_at = now + timedelta(seconds=window_seconds)

    query_started = datetime.now(timezone.utc)
    try:
        counter = RateLimitCounter.objects(
            scope=scope,
            key=key,
            bucket_epoch=bucket_epoch,
        ).modify(
            upsert=True,
            new=True,
            inc__count=1,
            set_on_insert__scope=scope,
            set_on_insert__key=key,
            set_on_insert__bucket_epoch=bucket_epoch,
            set_on_insert__window_seconds=window_seconds,
            set_on_insert__expires_at=expires_at,
        )
    except (ValidationError, NotUniqueError, OperationError) as exc:
        logger.log_error(
            "rate_limit_query_failed",
            exception=exc,
            context={
                "scope": scope,
                "key": key,
                "bucket_epoch": bucket_epoch,
            },
        )
        raise

    current_count = int(counter.count)
    remaining = max(0, max_requests - current_count)
    limited = current_count > max_requests
    retry_after = max(1, int((counter.expires_at - now).total_seconds()))

    result = {
        "limited": limited,
        "remaining": remaining,
        "retry_after": retry_after,
    }
    logger.log_debug(
        "rate_limit_query_succeeded",
        context={
            "scope": scope,
            "key": key,
            "duration_ms": round(
                (datetime.now(timezone.utc) - query_started).total_seconds() * 1000, 2
            ),
            "current_count": current_count,
            "limited": limited,
        },
    )
    return result


def log_session_audit_event(
    *,
    actor_user_uuid: str,
    target_user_uuid: str,
    action: str,
    session_uuid: str | None = None,
    reason: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    metadata: Dict[str, Any] | None = None,
) -> None:
    logger.log_debug(
        "audit_log_create_started",
        context={
            "action": action,
            "actor_user_uuid": actor_user_uuid,
            "target_user_uuid": target_user_uuid,
        },
    )
    retention_days = int(
        current_app.config.get(
            "AUDIT_LOG_RETENTION_DAYS",
            BaseConfig.AUDIT_LOG_RETENTION_DAYS,
        )
    )
    expires_at = utcnow() + timedelta(days=retention_days)

    try:
        SessionAuditLog(
            actor_user_uuid=actor_user_uuid,
            target_user_uuid=target_user_uuid,
            session_uuid=session_uuid,
            action=action,
            reason=reason,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata=metadata or {},
            expires_at=expires_at,
        ).save()
    except (ValidationError, NotUniqueError, OperationError) as exc:
        logger.log_error(
            "audit_log_create_failed",
            exception=exc,
            context={
                "action": action,
                "actor_user_uuid": actor_user_uuid,
                "target_user_uuid": target_user_uuid,
            },
        )
        raise
    logger.log_app_event(
        "audit_log_created",
        context={
            "action": action,
            "actor_user_uuid": actor_user_uuid,
            "target_user_uuid": target_user_uuid,
        },
    )
