from __future__ import annotations

from typing import Literal

from app.schemas.form import FormCreateInput
from app.schemas.mappers import to_json_ready

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


@health_api.get("/health", tags=[system_tag], responses={200: HealthResponse})
def health():
    response = HealthResponse(status="ok", service="form")
    return to_json_ready(response)


@health_api.post("/schemas/echo-form", tags=[schema_tag], responses={200: FormCreateInput})
def echo_form(body: FormCreateInput):
    """Accept a form schema payload and return it back as validated JSON."""
    return to_json_ready(body)
