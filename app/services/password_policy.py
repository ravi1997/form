from __future__ import annotations

from datetime import timedelta
from typing import Iterable

from flask import current_app

from app.config import BaseConfig
from app.models.user import User
from app.utils import utcnow


def max_password_expire_days() -> int:
    return BaseConfig.get_int(
        current_app.config,
        "MAX_PASSWORD_EXPIRE_DAYS",
        BaseConfig.MAX_PASSWORD_EXPIRE_DAYS,
    )


def should_force_password_change(user: User) -> bool:
    if not user.password_hash:
        return False
    if bool(getattr(user, "must_change_password", False)):
        return True
    last_change = getattr(user, "last_password_change_at", None) or getattr(
        user, "created_at", None
    )
    if not last_change:
        return False
    expire_after = timedelta(days=max_password_expire_days())
    return last_change <= utcnow() - expire_after


def enforce_password_expiry(users: Iterable[User] | None = None) -> int:
    queryset = users if users is not None else User.objects(auth_provider="local")
    updated = 0
    for user in queryset:
        if not should_force_password_change(user):
            continue
        if not bool(getattr(user, "must_change_password", False)):
            user.must_change_password = True
            user.save()
            updated += 1
    return updated
