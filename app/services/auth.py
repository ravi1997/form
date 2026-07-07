from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

import jwt
from flask import current_app

from app.config import BaseConfig
from app.models.auth import TokenBlocklist, UserSession


class AuthError(Exception):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _jwt_secret() -> str:
    secret = current_app.config.get("JWT_SECRET_KEY")
    if not secret:
        raise AuthError("JWT secret is not configured")
    return secret


def _jwt_algorithm() -> str:
    return current_app.config.get("JWT_ALGORITHM", BaseConfig.JWT_ALGORITHM)


def access_token_ttl_seconds() -> int:
    minutes = int(
        current_app.config.get(
            "JWT_ACCESS_TOKEN_EXPIRES_MINUTES",
            BaseConfig.JWT_ACCESS_TOKEN_EXPIRES_MINUTES,
        )
    )
    return minutes * 60


def _refresh_token_ttl_seconds() -> int:
    days = int(current_app.config.get("JWT_REFRESH_TOKEN_EXPIRES_DAYS", BaseConfig.JWT_REFRESH_TOKEN_EXPIRES_DAYS))
    return days * 24 * 60 * 60


def create_access_token(user_uuid: str, email: str, session_uuid: str) -> str:
    now = _utcnow()
    ttl = access_token_ttl_seconds()
    payload = {
        "sub": user_uuid,
        "email": email,
        "sid": session_uuid,
        "jti": str(uuid4()),
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=ttl)).timestamp()),
    }
    return jwt.encode(payload, _jwt_secret(), algorithm=_jwt_algorithm())


def create_refresh_token(user_uuid: str, email: str, session_uuid: str) -> str:
    now = _utcnow()
    ttl = _refresh_token_ttl_seconds()
    payload = {
        "sub": user_uuid,
        "email": email,
        "sid": session_uuid,
        "jti": str(uuid4()),
        "type": "refresh",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=ttl)).timestamp()),
    }
    return jwt.encode(payload, _jwt_secret(), algorithm=_jwt_algorithm())


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def decode_token(token: str, expected_type: str) -> Dict[str, Any]:
    try:
        payload = jwt.decode(token, _jwt_secret(), algorithms=[_jwt_algorithm()])
    except jwt.ExpiredSignatureError as exc:
        raise AuthError("Token has expired") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthError("Invalid token") from exc

    token_type = payload.get("type")
    if token_type != expected_type:
        raise AuthError(f"Expected {expected_type} token")

    subject = payload.get("sub")
    email = payload.get("email")
    session_uuid = payload.get("sid")
    jti = payload.get("jti")
    exp = payload.get("exp")
    if not subject or not email or not session_uuid or not jti or not exp:
        raise AuthError("Token payload is invalid")

    return {
        "sub": str(subject),
        "email": str(email),
        "sid": str(session_uuid),
        "jti": str(jti),
        "exp": int(exp),
        "type": str(token_type),
    }


def create_user_session(
    *,
    user_uuid: str,
    email: str,
    user_agent: Optional[str] = None,
    ip_address: Optional[str] = None,
    device_name: Optional[str] = None,
) -> Dict[str, str | int]:
    session_uuid = str(uuid4())
    refresh_token = create_refresh_token(user_uuid=user_uuid, email=email, session_uuid=session_uuid)
    refresh_payload = decode_token(refresh_token, expected_type="refresh")
    access_token = create_access_token(user_uuid=user_uuid, email=email, session_uuid=session_uuid)

    expires_at = datetime.fromtimestamp(refresh_payload["exp"], tz=timezone.utc)
    UserSession(
        session_uuid=session_uuid,
        user_uuid=user_uuid,
        email=email,
        refresh_jti=refresh_payload["jti"],
        refresh_token_hash=_token_hash(refresh_token),
        refresh_expires_at=expires_at,
        device_name=device_name,
        user_agent=user_agent,
        ip_address=ip_address,
    ).save()

    return {
        "session_uuid": session_uuid,
        "access_token": access_token,
        "refresh_token": refresh_token,
    }


def get_session(session_uuid: str, user_uuid: str) -> Optional[UserSession]:
    return UserSession.objects(session_uuid=session_uuid, user_uuid=user_uuid, is_active=True).first()


def list_active_sessions(user_uuid: str) -> List[UserSession]:
    return list(UserSession.objects(user_uuid=user_uuid, is_active=True).order_by("-last_seen_at"))


def get_session_by_uuid(session_uuid: str) -> Optional[UserSession]:
    return UserSession.objects(session_uuid=session_uuid).first()


def touch_session(session_uuid: str, user_uuid: str) -> None:
    session = get_session(session_uuid=session_uuid, user_uuid=user_uuid)
    if not session:
        return
    session.last_seen_at = datetime.utcnow()
    session.save()


def is_refresh_token_revoked(token: str, payload: Dict[str, Any] | None = None) -> bool:
    resolved_payload = payload or decode_token(token, expected_type="refresh")

    session = get_session(session_uuid=resolved_payload["sid"], user_uuid=resolved_payload["sub"])
    if not session:
        return True

    if session.refresh_jti != resolved_payload["jti"]:
        return True

    if session.refresh_token_hash != _token_hash(token):
        return True

    if TokenBlocklist.objects(jti=resolved_payload["jti"]).first():
        return True

    return bool(TokenBlocklist.objects(token_hash=_token_hash(token)).first())


def revoke_refresh_token(token: str, reason: str = "logout") -> None:
    payload = decode_token(token, expected_type="refresh")

    if is_refresh_token_revoked(token, payload=payload):
        revoke_session(session_uuid=payload["sid"], user_uuid=payload["sub"], reason=reason)
        return

    expires_at = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    TokenBlocklist(
        jti=payload["jti"],
        token_hash=_token_hash(token),
        user_uuid=payload["sub"],
        token_type="refresh",
        expires_at=expires_at,
        reason=reason,
    ).save()

    revoke_session(session_uuid=payload["sid"], user_uuid=payload["sub"], reason=reason)


def rotate_refresh_token(token: str) -> Dict[str, Any]:
    payload = decode_token(token, expected_type="refresh")
    if is_refresh_token_revoked(token, payload=payload):
        raise AuthError("Refresh token has been revoked")

    session = get_session(session_uuid=payload["sid"], user_uuid=payload["sub"])
    if not session:
        raise AuthError("Session not found")

    old_hash = _token_hash(token)
    if session.refresh_token_hash != old_hash or session.refresh_jti != payload["jti"]:
        raise AuthError("Refresh token does not match active session")

    if not TokenBlocklist.objects(jti=payload["jti"]).first():
        expires_at = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        TokenBlocklist(
            jti=payload["jti"],
            token_hash=old_hash,
            user_uuid=payload["sub"],
            token_type="refresh",
            expires_at=expires_at,
            reason="refresh_rotation",
        ).save()

    new_refresh_token = create_refresh_token(
        user_uuid=payload["sub"],
        email=payload["email"],
        session_uuid=payload["sid"],
    )
    new_refresh_payload = decode_token(new_refresh_token, expected_type="refresh")

    session.refresh_jti = new_refresh_payload["jti"]
    session.refresh_token_hash = _token_hash(new_refresh_token)
    session.refresh_expires_at = datetime.fromtimestamp(new_refresh_payload["exp"], tz=timezone.utc)
    session.last_seen_at = datetime.utcnow()
    session.save()

    new_access_token = create_access_token(
        user_uuid=payload["sub"],
        email=payload["email"],
        session_uuid=payload["sid"],
    )

    return {
        "access_token": new_access_token,
        "refresh_token": new_refresh_token,
        "session_uuid": payload["sid"],
        "sub": payload["sub"],
    }


def revoke_session(session_uuid: str, user_uuid: str, reason: str = "logout") -> bool:
    session = get_session(session_uuid=session_uuid, user_uuid=user_uuid)
    if not session:
        return False

    if not TokenBlocklist.objects(jti=session.refresh_jti).first():
        TokenBlocklist(
            jti=session.refresh_jti,
            token_hash=session.refresh_token_hash,
            user_uuid=user_uuid,
            token_type="refresh",
            expires_at=session.refresh_expires_at,
            reason=reason,
        ).save()

    session.is_active = False
    session.revoked_at = datetime.utcnow()
    session.revoked_reason = reason
    session.last_seen_at = datetime.utcnow()
    session.save()
    return True


def revoke_all_sessions(user_uuid: str, reason: str = "logout_all", except_session_uuid: str | None = None) -> int:
    count = 0
    active_sessions = UserSession.objects(user_uuid=user_uuid, is_active=True)
    for session in active_sessions:
        if except_session_uuid and session.session_uuid == except_session_uuid:
            continue
        if revoke_session(session_uuid=session.session_uuid, user_uuid=user_uuid, reason=reason):
            count += 1
    return count
