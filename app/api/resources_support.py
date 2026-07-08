"""Blueprint, tags, request hooks, and logger for the resources API."""

from __future__ import annotations

from flask import g, request
from app.services.auth import AuthError
from app.services.rbac import (
    has_global_admin_privileges,
    resolve_access_identity_from_header,
    get_user_by_uuid,
)
from app.services import get_rotating_logger
from app.api.resources_utils import (
    after_resources_request_logging,
    authorize_resources_route as _authorize_resources_route,
    before_resources_request_logging,
    resources_rate_limit as _resources_rate_limit,
    security_event as _security_event,
)

try:
    from flask_openapi3 import APIBlueprint, Tag
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("flask-openapi3 is required") from exc

resources_tag = Tag(
    name="Resources", description="Project/Form/Section/Question resource APIs"
)
version_tag = Tag(name="Versions", description="Version append/update APIs")
resources_api = APIBlueprint("resources", __name__, url_prefix="/api/v1")
logger = get_rotating_logger()


def _error(message: str, status: int = 400):
    from app.schemas.mappers import to_json_ready
    from app.api.resources_schemas import ErrorResponse

    return to_json_ready(ErrorResponse(message=message)), status


@resources_api.before_request
def _before_resources_request():
    before_resources_request_logging()

    throttle = _resources_rate_limit()
    if throttle:
        logger.log_debug(
            "resources_api_throttled",
            context={
                "method": request.method,
                "path": request.path,
                "request_id": getattr(g, "resources_request_id", None),
            },
        )
        return throttle

    try:
        raw_authorization = request.headers.get("Authorization", "")
        payload = resolve_access_identity_from_header(raw_authorization)
        user = get_user_by_uuid(payload["sub"])
        g.resources_user_payload = payload
        g.resources_user = user
    except AuthError as exc:
        _security_event(event="resources_auth", outcome="failed", reason=str(exc))
        return _error(str(exc), 401)

    authz = _authorize_resources_route(has_global_admin_privileges)
    if authz:
        return authz


@resources_api.after_request
def _after_resources_request(response):
    return after_resources_request_logging(response)
