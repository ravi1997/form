from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from flask import current_app

from app.config import BaseConfig
from app.models.auth import RateLimitCounter, SessionAuditLog


def utcnow() -> datetime:
    # Keep naive UTC to match mongoengine DateTimeField values in rate-limit math.
    return datetime.now(timezone.utc).replace(tzinfo=None)


def check_and_increment_rate_limit(
    *,
    scope: str,
    key: str,
    max_requests: int,
    window_seconds: int,
) -> Dict[str, int | bool]:
    now = utcnow()
    bucket_epoch = int(now.timestamp()) // window_seconds
    expires_at = now + timedelta(seconds=window_seconds)

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

    current_count = int(counter.count)
    remaining = max(0, max_requests - current_count)
    limited = current_count > max_requests
    retry_after = max(1, int((counter.expires_at - now).total_seconds()))

    return {
        "limited": limited,
        "remaining": remaining,
        "retry_after": retry_after,
    }


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
    retention_days = int(
        current_app.config.get(
            "AUDIT_LOG_RETENTION_DAYS",
            BaseConfig.AUDIT_LOG_RETENTION_DAYS,
        )
    )
    expires_at = utcnow() + timedelta(days=retention_days)

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
