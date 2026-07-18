from __future__ import annotations

import base64
import binascii
from datetime import datetime
from typing import Optional

from flask import current_app, g, request

from app.config import BaseConfig
from app.schemas.auth import AuthorizationHeader, ErrorResponse
from app.schemas.mappers import to_json_ready
from app.services import get_rotating_logger
from app.services.auth import AuthError
from app.services.rbac import (
    require_admin_for_user_payload,
    require_global_admin_by_payload,
    resolve_access_identity_from_header,
)
from app.services.security import log_session_audit_event
from app.utils import client_ip, utcnow

try:
    from flask_openapi3 import APIBlueprint, Tag
except ImportError as exc:  # pragma: no cover - evaluated only when package is missing
    raise RuntimeError(
        "flask-openapi3 is required for OpenAPI integration. Install with: pip install flask-openapi3"
    ) from exc


auth_tag = Tag(name="Auth", description="JWT authentication")
auth_api = APIBlueprint("auth", __name__, url_prefix="/api/v1/auth")
logger = get_rotating_logger()


@auth_api.before_request
def _auth_before_request_logging():
    logger.log_app_event(
        "API Started",
        context={
            "route": f"{request.method} {request.path}",
            "endpoint": request.endpoint,
            "request_id": getattr(g, "request_id", None),
            "user_id": getattr(g, "user_id", None),
        },
    )


@auth_api.after_request
def _auth_after_request_logging(response):
    logger.log_app_event(
        "API Completed",
        context={
            "route": f"{request.method} {request.path}",
            "endpoint": request.endpoint,
            "status_code": response.status_code,
            "request_id": getattr(g, "request_id", None),
            "user_id": getattr(g, "user_id", None),
        },
    )
    return response


def _unauthorized(message: str):
    return to_json_ready(ErrorResponse(message=message)), 401


def _bad_request(message: str):
    return to_json_ready(ErrorResponse(message=message)), 400


def _is_audit_enabled() -> bool:
    return BaseConfig.get_bool(
        current_app.config,
        "ENABLE_AUDIT_LOGS",
        BaseConfig.ENABLE_AUDIT_LOGS,
    )


def _audit_log(**kwargs):
    if _is_audit_enabled():
        metadata = dict(kwargs.get("metadata") or {})
        metadata["request_id"] = getattr(g, "request_id", None)
        kwargs["metadata"] = metadata
        log_session_audit_event(**kwargs)


def _security_event(
    *,
    event: str,
    outcome: str,
    endpoint: str,
    actor_user_uuid: Optional[str] = None,
    target_user_uuid: Optional[str] = None,
    limit_scope: Optional[str] = None,
    reason: Optional[str] = None,
    details: Optional[dict] = None,
):
    payload = {
        "event": event,
        "outcome": outcome,
        "endpoint": endpoint,
        "ip": client_ip(),
        "actor_user_uuid": actor_user_uuid,
        "target_user_uuid": target_user_uuid,
        "limit_scope": limit_scope,
        "reason": reason,
        "details": details or {},
        "request_id": getattr(g, "request_id", None),
        "timestamp": utcnow().isoformat().replace("+00:00", "Z"),
    }
    logger.log_app_event("security_event", context=payload)


def _encode_audit_cursor(created_at: datetime) -> str:
    return base64.urlsafe_b64encode(created_at.isoformat().encode("utf-8")).decode(
        "utf-8"
    )


def _decode_audit_cursor(cursor: str) -> datetime:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("utf-8")).decode("utf-8")
        return datetime.fromisoformat(raw)
    except (ValueError, UnicodeDecodeError, binascii.Error) as exc:
        raise AuthError("Invalid cursor") from exc


def _extract_bearer(header: AuthorizationHeader):
    raw = header.Authorization.strip()
    if not raw.startswith("Bearer "):
        raise AuthError("Authorization header must use Bearer token")
    return raw.replace("Bearer ", "", 1).strip()


def _resolve_access_identity(header: AuthorizationHeader):
    return resolve_access_identity_from_header(header.Authorization)


def _require_admin(header: AuthorizationHeader):
    payload = _resolve_access_identity(header)
    return require_global_admin_by_payload(payload)


def _require_admin_for_user(header: AuthorizationHeader, target_user_uuid: str):
    payload = _resolve_access_identity(header)
    return require_admin_for_user_payload(payload, target_user_uuid)
