"""JWT authentication service.

Provides token creation (access + refresh), validation, rotation, revocation,
and session lifecycle management.  All tokens carry a ``typ`` claim (``access``
or ``refresh``) and a ``kid`` header for multi-key rotation via JWT_ADDITIONAL_KEYS.

Token blocklisting is backed by the ``token_blocklist`` MongoDB collection with
a TTL index aligned to the refresh token expiry.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

import jwt
from flask import current_app

from app.config import BaseConfig
from app.models.auth import TokenBlocklist, UserSession
from app.services import get_rotating_logger

logger = get_rotating_logger()

_JWT_KID_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")


class AuthError(Exception):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _jwt_secret() -> str:
    secret = current_app.config.get("JWT_SECRET_KEY")
    if not secret:
        raise AuthError("JWT secret is not configured")
    return secret


def _jwt_active_kid() -> str:
    kid = current_app.config.get("JWT_ACTIVE_KID", BaseConfig.JWT_ACTIVE_KID)
    if not kid:
        raise AuthError("JWT active key id is not configured")
    return str(kid)


def _jwt_keyring() -> Dict[str, str]:
    keyring = {_jwt_active_kid(): _jwt_secret()}

    additional = current_app.config.get(
        "JWT_ADDITIONAL_KEYS", BaseConfig.JWT_ADDITIONAL_KEYS
    )
    if additional and isinstance(additional, dict):
        now = _utcnow()
        for kid, raw_value in additional.items():
            if not kid or not raw_value:
                continue
            key_id = str(kid)
            if not _JWT_KID_PATTERN.fullmatch(key_id):
                logger.log_app_event(
                    "jwt_additional_key_rejected",
                    level="WARNING",
                    context={"kid": key_id, "reason": "invalid_kid_format"},
                )
                continue
            if isinstance(raw_value, dict):
                secret = raw_value.get("secret")
                expires_at = raw_value.get("expires_at")
                if not secret:
                    continue
                if expires_at:
                    expires_value = (
                        expires_at
                        if isinstance(expires_at, datetime)
                        else datetime.fromisoformat(str(expires_at))
                    )
                    if expires_value.tzinfo is None:
                        expires_value = expires_value.replace(tzinfo=timezone.utc)
                    if expires_value <= now:
                        logger.log_app_event(
                            "jwt_additional_key_expired",
                            level="WARNING",
                            context={"kid": key_id},
                        )
                        continue
                keyring[key_id] = str(secret)
            else:
                keyring[key_id] = str(raw_value)

    return keyring


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
    days = int(
        current_app.config.get(
            "JWT_REFRESH_TOKEN_EXPIRES_DAYS", BaseConfig.JWT_REFRESH_TOKEN_EXPIRES_DAYS
        )
    )
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
        "kid": _jwt_active_kid(),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=ttl)).timestamp()),
    }
    return jwt.encode(
        payload,
        _jwt_secret(),
        algorithm=_jwt_algorithm(),
        headers={"kid": _jwt_active_kid()},
    )


def create_refresh_token(user_uuid: str, email: str, session_uuid: str) -> str:
    now = _utcnow()
    ttl = _refresh_token_ttl_seconds()
    payload = {
        "sub": user_uuid,
        "email": email,
        "sid": session_uuid,
        "jti": str(uuid4()),
        "type": "refresh",
        "kid": _jwt_active_kid(),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=ttl)).timestamp()),
    }
    return jwt.encode(
        payload,
        _jwt_secret(),
        algorithm=_jwt_algorithm(),
        headers={"kid": _jwt_active_kid()},
    )


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def decode_token(token: str, expected_type: str) -> Dict[str, Any]:
    logger.log_debug("jwt_decode_started", context={"expected_type": expected_type})
    token_kid = None
    keyring = _jwt_keyring()

    try:
        token_kid = jwt.get_unverified_header(token).get("kid")
    except jwt.InvalidTokenError:
        token_kid = None

    if token_kid and not _JWT_KID_PATTERN.fullmatch(str(token_kid)):
        logger.log_app_event(
            "jwt_kid_rejected",
            level="WARNING",
            context={"expected_type": expected_type, "kid": str(token_kid)},
        )
        raise AuthError("Invalid token")

    keys_to_try: List[tuple[str, str]] = []
    if token_kid and token_kid in keyring:
        keys_to_try.append((token_kid, keyring[token_kid]))

    for kid, key in keyring.items():
        if token_kid and kid == token_kid:
            continue
        keys_to_try.append((kid, key))

    last_error: Exception | None = None
    payload = None
    try:
        decoded_kid = None
        for kid, key in keys_to_try:
            try:
                payload = jwt.decode(token, key, algorithms=[_jwt_algorithm()])
                decoded_kid = kid
                break
            except jwt.ExpiredSignatureError as exc:
                last_error = exc
                continue
            except jwt.InvalidTokenError as exc:
                last_error = exc
                continue

        if payload is None:
            if isinstance(last_error, jwt.ExpiredSignatureError):
                logger.log_app_event(
                    "jwt_token_expired",
                    level="WARNING",
                    context={"expected_type": expected_type},
                )
                raise AuthError("Token has expired") from last_error
            logger.log_app_event(
                "jwt_decode_failed",
                level="WARNING",
                context={"expected_type": expected_type},
            )
            raise AuthError("Invalid token") from last_error
    except AuthError:
        raise

    token_type = payload.get("type")
    if token_type != expected_type:
        logger.log_app_event(
            "jwt_type_mismatch",
            level="WARNING",
            context={"expected_type": expected_type, "actual_type": token_type},
        )
        raise AuthError(f"Expected {expected_type} token")

    subject = payload.get("sub")
    email = payload.get("email")
    session_uuid = payload.get("sid")
    jti = payload.get("jti")
    kid = payload.get("kid")
    exp = payload.get("exp")
    if not subject or not email or not session_uuid or not jti or not exp:
        logger.log_app_event(
            "jwt_payload_invalid",
            level="WARNING",
            context={"expected_type": expected_type},
        )
        raise AuthError("Token payload is invalid")

    logger.log_debug(
        "jwt_decode_successful",
        context={"expected_type": expected_type, "user_uuid": str(subject)},
    )
    active_kid = _jwt_active_kid()
    if decoded_kid and decoded_kid != active_kid:
        logger.log_app_event(
            "jwt_validated_with_non_active_key",
            level="WARNING",
            context={
                "expected_type": expected_type,
                "kid": decoded_kid,
                "active_kid": active_kid,
            },
        )
    return {
        "sub": str(subject),
        "email": str(email),
        "sid": str(session_uuid),
        "jti": str(jti),
        "kid": str(kid) if kid else str(token_kid or ""),
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
    logger.log_debug(
        "create_user_session_started", context={"user_uuid": user_uuid, "email": email}
    )
    session_uuid = str(uuid4())
    refresh_token = create_refresh_token(
        user_uuid=user_uuid, email=email, session_uuid=session_uuid
    )
    refresh_payload = decode_token(refresh_token, expected_type="refresh")
    access_token = create_access_token(
        user_uuid=user_uuid, email=email, session_uuid=session_uuid
    )

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
    logger.log_app_event(
        "user_session_created",
        context={"user_uuid": user_uuid, "session_uuid": session_uuid},
    )

    return {
        "session_uuid": session_uuid,
        "access_token": access_token,
        "refresh_token": refresh_token,
    }


def get_session(session_uuid: str, user_uuid: str) -> Optional[UserSession]:
    return UserSession.objects(
        session_uuid=session_uuid, user_uuid=user_uuid, is_active=True
    ).first()


def list_active_sessions(user_uuid: str) -> List[UserSession]:
    return list(
        UserSession.objects(user_uuid=user_uuid, is_active=True).order_by(
            "-last_seen_at"
        )
    )


def get_session_by_uuid(session_uuid: str) -> Optional[UserSession]:
    return UserSession.objects(session_uuid=session_uuid).first()


def touch_session(session_uuid: str, user_uuid: str) -> None:
    session = get_session(session_uuid=session_uuid, user_uuid=user_uuid)
    if not session:
        return
    session.last_seen_at = _utcnow()
    session.save()


def is_refresh_token_revoked(token: str, payload: Dict[str, Any] | None = None) -> bool:
    resolved_payload = payload or decode_token(token, expected_type="refresh")

    session = get_session(
        session_uuid=resolved_payload["sid"], user_uuid=resolved_payload["sub"]
    )
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
    logger.log_debug("revoke_refresh_token_started", context={"reason": reason})
    payload = decode_token(token, expected_type="refresh")

    if is_refresh_token_revoked(token, payload=payload):
        revoke_session(
            session_uuid=payload["sid"], user_uuid=payload["sub"], reason=reason
        )
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
    logger.log_app_event(
        "refresh_token_revoked",
        context={
            "reason": reason,
            "user_uuid": payload["sub"],
            "session_uuid": payload["sid"],
        },
    )


def rotate_refresh_token(token: str) -> Dict[str, Any]:
    logger.log_debug("refresh_token_rotation_started")
    payload = decode_token(token, expected_type="refresh")
    if is_refresh_token_revoked(token, payload=payload):
        logger.log_app_event(
            "refresh_token_rotation_failed",
            level="WARNING",
            context={"reason": "token_revoked", "user_uuid": payload.get("sub")},
        )
        raise AuthError("Refresh token has been revoked")

    session = get_session(session_uuid=payload["sid"], user_uuid=payload["sub"])
    if not session:
        logger.log_app_event(
            "refresh_token_rotation_failed",
            level="WARNING",
            context={"reason": "session_not_found", "user_uuid": payload.get("sub")},
        )
        raise AuthError("Session not found")

    old_hash = _token_hash(token)
    if session.refresh_token_hash != old_hash or session.refresh_jti != payload["jti"]:
        logger.log_app_event(
            "refresh_token_rotation_failed",
            level="WARNING",
            context={
                "reason": "token_session_mismatch",
                "user_uuid": payload.get("sub"),
            },
        )
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
    session.refresh_expires_at = datetime.fromtimestamp(
        new_refresh_payload["exp"], tz=timezone.utc
    )
    session.last_seen_at = _utcnow()
    session.save()

    new_access_token = create_access_token(
        user_uuid=payload["sub"],
        email=payload["email"],
        session_uuid=payload["sid"],
    )

    rotated = {
        "access_token": new_access_token,
        "refresh_token": new_refresh_token,
        "session_uuid": payload["sid"],
        "sub": payload["sub"],
    }
    logger.log_app_event(
        "refresh_token_rotated",
        context={"user_uuid": payload["sub"], "session_uuid": payload["sid"]},
    )
    return rotated


def revoke_session(session_uuid: str, user_uuid: str, reason: str = "logout") -> bool:
    logger.log_debug(
        "revoke_session_started",
        context={
            "session_uuid": session_uuid,
            "user_uuid": user_uuid,
            "reason": reason,
        },
    )
    session = get_session(session_uuid=session_uuid, user_uuid=user_uuid)
    if not session:
        logger.log_app_event(
            "revoke_session_noop",
            level="WARNING",
            context={
                "session_uuid": session_uuid,
                "user_uuid": user_uuid,
                "reason": reason,
            },
        )
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
    session.revoked_at = _utcnow()
    session.revoked_reason = reason
    session.last_seen_at = _utcnow()
    session.save()
    logger.log_app_event(
        "session_revoked",
        context={
            "session_uuid": session_uuid,
            "user_uuid": user_uuid,
            "reason": reason,
        },
    )
    return True


def revoke_all_sessions(
    user_uuid: str, reason: str = "logout_all", except_session_uuid: str | None = None
) -> int:
    count = 0
    active_sessions = UserSession.objects(user_uuid=user_uuid, is_active=True)
    for session in active_sessions:
        if except_session_uuid and session.session_uuid == except_session_uuid:
            continue
        if revoke_session(
            session_uuid=session.session_uuid, user_uuid=user_uuid, reason=reason
        ):
            count += 1
    return count
