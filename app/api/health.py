from __future__ import annotations

from typing import Literal

from mongoengine.connection import get_connection
from pymongo.errors import PyMongoError

from app.middleware.observability import get_metrics_snapshot
from app.schemas.form import FormCreateInput
from app.schemas.mappers import to_json_ready
from app.services.condition_management_async import get_async_queue_status

try:
    from flask_openapi3 import APIBlueprint, Tag
except ImportError as exc:  # pragma: no cover - evaluated only when package is missing
    raise RuntimeError(
        "flask-openapi3 is required for OpenAPI integration. Install with: pip install flask-openapi3"
    ) from exc

from app.schemas.common import SchemaModel

system_tag = Tag(name="System", description="System and integration checks")
schema_tag = Tag(name="Schemas", description="Schema validation and JSON IO examples")

health_api = APIBlueprint("health", __name__, url_prefix="/api/v1")


class HealthResponse(SchemaModel):
    status: Literal["ok"]
    service: str


class LivenessResponse(SchemaModel):
    status: Literal["alive"]
    service: str


class ReadinessResponse(SchemaModel):
    status: Literal["ready", "degraded"]
    service: str
    database: Literal["ok", "error"]


@health_api.get("/health", tags=[system_tag], responses={200: HealthResponse})
def health():
    response = HealthResponse(status="ok", service="form")
    return to_json_ready(response)


@health_api.get("/liveness", tags=[system_tag], responses={200: LivenessResponse})
def liveness():
    return to_json_ready(LivenessResponse(status="alive", service="form"))


@health_api.get("/readiness", tags=[system_tag], responses={200: ReadinessResponse})
def readiness():
    try:
        get_connection().admin.command("ping")
    except PyMongoError:
        return (
            to_json_ready(
                ReadinessResponse(status="degraded", service="form", database="error")
            ),
            503,
        )
    return to_json_ready(
        ReadinessResponse(status="ready", service="form", database="ok")
    )


@health_api.get("/metrics", tags=[system_tag])
def metrics():
    snapshot = get_metrics_snapshot()
    snapshot["async_queue"] = get_async_queue_status()
    return to_json_ready(snapshot)


@health_api.post(
    "/schemas/echo-form", tags=[schema_tag], responses={200: FormCreateInput}
)
def echo_form(body: FormCreateInput):
    """Accept a form schema payload and return it back as validated JSON."""
    return to_json_ready(body)
